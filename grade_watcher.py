import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

COURSE_KEYS = ["MO340", "ΜΟ340", "Στρατηγική Επιχειρήσεων"]
COURSE_NAME = "MO340"
SEND_CHECK_MESSAGES = True

LOGIN_URL = "https://dias.ionio.gr/"
GRADES_SELECTOR = "body"
STATE_FILE = Path("state/course_hash.txt")

USERNAME = os.environ["DIAS_USER"]
PASSWORD = os.environ["DIAS_PASS"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
GRADES_URL = os.getenv("GRADES_URL", "").strip()


def now() -> str:
    return datetime.now(ZoneInfo("Europe/Athens")).strftime("%H:%M")


def send_telegram(msg: str, silent: bool = False) -> None:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg[:4000],
                  "disable_notification": silent},
            timeout=20,
        )
        print("telegram:", r.status_code)
    except Exception as e:
        print("telegram αποτυχία:", type(e).__name__)


def send_photo(path: str, caption: str) -> None:
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                data={"chat_id": TG_CHAT_ID, "caption": caption[:1000],
                      "disable_notification": True},
                files={"photo": f},
                timeout=30,
            )
    except Exception as e:
        print("telegram photo αποτυχία:", type(e).__name__)


def fetch_page_text() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="el-GR", timezone_id="Europe/Athens")
        page.set_default_timeout(60_000)

        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#username")
        page.fill("#username", USERNAME)
        page.fill("input[type=password]", PASSWORD)
        page.locator("button[type=submit], input[type=submit], "
                     "button[name=submit]").first.click(no_wait_after=True)

        try:
            page.wait_for_url(lambda u: "sso.ionio.gr" not in u, timeout=60_000)
        except Exception:
            page.screenshot(path="login_error.png")
            browser.close()
            send_photo("login_error.png", "Το login στo DIAS δεν ολοκληρώθηκε.")
            raise RuntimeError("login failed")

        page.wait_for_load_state("load")
        if GRADES_URL:
            page.goto(GRADES_URL, wait_until="load")
        page.wait_for_timeout(4000)
        page.wait_for_selector(GRADES_SELECTOR)
        text = page.inner_text(GRADES_SELECTOR)
        browser.close()

    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def main() -> int:
    STATE_FILE.parent.mkdir(exist_ok=True)

    try:
        text = fetch_page_text()
    except Exception as e:
        print("σφάλμα:", type(e).__name__)
        send_telegram(f"{now()} — ο έλεγχος απέτυχε ({type(e).__name__}). "
                      "Θα ξαναδοκιμάσω σε λίγο.", silent=True)
        return 1

    found = [l for l in text.splitlines() if any(k in l for k in COURSE_KEYS)]
    if not found:
        print("το μάθημα δεν βρέθηκε στη σελίδα")
        send_telegram(f"{now()} — δεν βρίσκω το {COURSE_NAME} στη σελίδα. "
                      "Έλεγξε το GRADES_URL.", silent=True)
        return 0

    current_hash = hashlib.sha256("\n".join(found).encode()).hexdigest()
    old_hash = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""
    STATE_FILE.write_text(current_hash)

    if not old_hash:
        print("πρώτη εκτέλεση: αποθηκεύτηκε αφετηρία")
        send_telegram(f"Ξεκίνησα από το cloud. Βρήκα το {COURSE_NAME}:\n\n"
                      + "\n".join(found), silent=True)
    elif current_hash != old_hash:
        print("ΑΛΛΑΓΗ στο μάθημα")
        send_telegram(f"!! ΒΓΗΚΕ Ο ΒΑΘΜΟΣ στο {COURSE_NAME}!!\n\n" + "\n".join(found))
    else:
        print("καμία αλλαγή")
        if SEND_CHECK_MESSAGES:
            send_telegram(f"{now()} — έλεγξα, τίποτα ακόμα στο {COURSE_NAME}",
                          silent=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())