"""
cricbuzz_score.py
------------------
Task A-1: Captures live cricket score from Cricbuzz → saves score.png
Task A-2: Sends score to WhatsApp contacts → extracts chat messages

Usage:  python cricbuzz_score.py
Setup:  pip install playwright && playwright install chromium
"""

import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ─────────────────────────────────────────────
#  EDIT YOUR CONTACTS HERE
# ─────────────────────────────────────────────

CONTACTS = [
    {"name": "dude",       "phone": "916385791987"},
    {"name": "D Nepolean", "phone": "917305467348"},
    {"name": "Easwar",     "phone": "919524827737"},
]

MESSAGES_TO_EXTRACT = 10
SESSION_DIR         = "wa_session"
REPORT_JSON         = "whatsapp_report.json"
REPORT_TXT          = "whatsapp_report.txt"


# ─────────────────────────────────────────────
#  WHATSAPP SELECTORS
# ─────────────────────────────────────────────

# Multiple login selectors — tries all until one works
WA_LOGGEDIN_SELECTORS = [
    'div[data-testid="chatlist-header"]',
    'div[data-testid="chat-list"]',
    'div#side',
    'div[aria-label="Chat list"]',
    'header',
]
WA_QR        = 'canvas[aria-label="Scan this QR code to link a device"]'
WA_MSG_INPUT_SELECTORS = [
    'div[data-testid="conversation-compose-box-input"]',
    'div[contenteditable="true"][data-tab="10"]',
    'div[contenteditable="true"][data-tab="6"]',
    'footer div[contenteditable="true"]',
]
WA_MSG_ROW   = 'div.message-in, div.message-out'
WA_MSG_TEXT  = 'span.selectable-text'
WA_MSG_TS    = 'div[data-testid="msg-meta"] span'


# ═══════════════════════════════════════════════════════════
#  TASK A-1 — Cricbuzz
# ═══════════════════════════════════════════════════════════

def get_cricket_score(browser) -> str:
    print("\n[Task A-1] Opening Cricbuzz …")
    page = browser.new_page()

    try:
        page.goto("https://www.cricbuzz.com/", wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        print("  ✗ Cricbuzz page load timed out.")
        page.screenshot(path="score.png", full_page=True)
        page.close()
        return "Could not load Cricbuzz."

    # Wait for page body to load
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        pass

    time.sleep(3)  # let JS render scores

    # Screenshot regardless
    page.screenshot(path="score.png", full_page=True)
    print("  ✓ Screenshot saved → score.png")

    # Extract score lines from full page text
    # Look for lines containing cricket keywords
    try:
        body_text = page.inner_text("body")
        keywords  = ["vs", " ov", "RR", "won by", "need", "innings", "CRR", "balls"]
        score_lines = []
        for line in body_text.splitlines():
            line = line.strip()
            if len(line) > 5 and any(k.lower() in line.lower() for k in keywords):
                score_lines.append(line)

        # Deduplicate while preserving order
        seen = set()
        unique_lines = []
        for line in score_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        score_lines = unique_lines[:8]  # top 8 relevant lines
    except Exception:
        score_lines = []

    if score_lines:
        result = "\n".join(score_lines)
        print(f"  ✓ Scores extracted:\n{result}\n")
    else:
        result = "No live matches found right now."
        print(f"  ℹ {result}\n")

    page.close()
    return result


# ═══════════════════════════════════════════════════════════
#  TASK A-2 — WhatsApp Web
# ═══════════════════════════════════════════════════════════

def wa_is_logged_in(page) -> bool:
    """Check if any login selector is present."""
    for sel in WA_LOGGEDIN_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                return True
        except Exception:
            continue
    return False


def wa_wait_for_login(page) -> bool:
    """Wait for QR scan or session restore. Returns True when logged in."""

    # Already logged in?
    if wa_is_logged_in(page):
        print("  ✓ Session restored — already logged in.")
        return True

    print("\n  📱 ACTION REQUIRED:")
    print("     Open WhatsApp on your phone")
    print("     → Linked Devices → Link a Device → Scan QR\n")
    print("  ⏳ Waiting up to 120 seconds for QR scan …\n")

    # Poll every 2 seconds for up to 120 seconds
    for i in range(60):
        time.sleep(2)
        if wa_is_logged_in(page):
            print("  ✓ Logged in successfully!")
            return True
        remaining = 120 - (i + 1) * 2
        if remaining > 0 and remaining % 20 == 0:
            print(f"  ⏳ {remaining} seconds remaining …")

    print("  ✗ QR scan timed out.")
    return False


def wa_get_input_box(page):
    """Try multiple selectors to find the message input box."""
    for sel in WA_MSG_INPUT_SELECTORS:
        try:
            el = page.wait_for_selector(sel, timeout=5_000)
            if el:
                return el, sel
        except PlaywrightTimeoutError:
            continue
    return None, None


def wa_open_chat(page, phone: str) -> bool:
    page.goto(
        f"https://web.whatsapp.com/send?phone={phone}",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    time.sleep(3)  # let chat fully load
    el, sel = wa_get_input_box(page)
    return el is not None


def wa_send(page, text: str) -> bool:
    try:
        el, sel = wa_get_input_box(page)
        if not el:
            print("    ✗ Message input box not found.")
            return False

        el.click()
        time.sleep(0.5)

        # Type line by line (Enter mid-message would send prematurely)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            page.keyboard.type(line, delay=20)
            if i < len(lines) - 1:
                page.keyboard.press("Shift+Enter")  # newline without sending

        time.sleep(0.5)
        page.keyboard.press("Enter")  # send
        time.sleep(2)
        return True
    except Exception as e:
        print(f"    ✗ Send failed: {e}")
        return False


def wa_extract(page, limit: int = 10) -> list[dict]:
    # Try multiple row selectors
    row_selectors = [
        'div.message-in, div.message-out',
        'div[class*="message-in"], div[class*="message-out"]',
        'div[data-id]',
    ]
    rows = []
    for sel in row_selectors:
        try:
            page.wait_for_selector(sel, timeout=5_000)
            rows = page.query_selector_all(sel)
            if rows:
                break
        except PlaywrightTimeoutError:
            continue

    if not rows:
        return []

    rows = rows[-limit:]
    msgs = []
    for row in rows:
        cls       = row.get_attribute("class") or ""
        direction = "sent" if "message-out" in cls else "received"

        # Try multiple text selectors
        text = ""
        for t_sel in ['span.selectable-text', 'span[dir="ltr"]', 'div[dir="ltr"]']:
            text_el = row.query_selector(t_sel)
            if text_el:
                text = text_el.inner_text().strip()
                if text:
                    break

        ts_el = row.query_selector(WA_MSG_TS)
        ts    = ts_el.inner_text().strip() if ts_el else ""

        if text:
            msgs.append({"direction": direction, "text": text, "timestamp": ts})
    return msgs


def save_report(report: list[dict]) -> None:
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    lines = [
        "WhatsApp Bot Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60, "",
    ]
    for e in report:
        lines.append(f"Contact : {e['name']}  ({e['phone']})")
        lines.append(f"Message : {e['message_sent']}")
        lines.append(f"Status  : {'✓ Sent' if e['sent'] else '✗ Failed'}")
        for m in e.get("extracted_messages", []):
            arrow = "→" if m["direction"] == "sent" else "←"
            lines.append(f"  {arrow} [{m['timestamp']}] {m['text']}")
        lines.append("")

    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  ✓ Reports saved → {REPORT_JSON} | {REPORT_TXT}")


def run_whatsapp(browser, score_text: str) -> None:
    print("\n[Task A-2] Opening WhatsApp Web …")
    page = browser.new_page()
    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=30_000)

    time.sleep(5)  # let page fully initialize

    if not wa_wait_for_login(page):
        print("  ✗ Could not log in. Skipping Task A-2.")
        page.close()
        return

    time.sleep(3)  # let chat list load after login

    report = []
    for contact in CONTACTS:
        name  = contact["name"]
        phone = contact["phone"]
        msg   = (
            f"Hi {name}! 🏏 Live Cricket Score Update:\n\n"
            f"{score_text}\n\n"
            f"— Sent by Playwright Bot 🤖"
        )

        print(f"\n  ─── {name} ({phone})")
        entry = {
            "name"              : name,
            "phone"             : phone,
            "message_sent"      : msg,
            "sent"              : False,
            "extracted_messages": [],
        }

        if not wa_open_chat(page, phone):
            print("  ✗ Could not open chat. Skipping.")
            report.append(entry)
            continue

        print("  ✓ Chat opened")
        entry["sent"] = wa_send(page, msg)
        print(f"  {'✓ Message sent' if entry['sent'] else '✗ Message failed'}")

        msgs = wa_extract(page, limit=MESSAGES_TO_EXTRACT)
        entry["extracted_messages"] = msgs
        print(f"  ✓ Extracted {len(msgs)} message(s)")
        for m in msgs[-3:]:
            arrow = "→" if m["direction"] == "sent" else "←"
            print(f"      {arrow} [{m['timestamp']}] {m['text'][:60]}")

        report.append(entry)
        time.sleep(2)

    save_report(report)
    page.close()


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    Path(SESSION_DIR).mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1280, "height": 900},
        )

        score_text = get_cricket_score(browser)
        run_whatsapp(browser, score_text)

        print("\nAll done. Closing in 3 seconds …")
        time.sleep(3)
        browser.close()


if __name__ == "__main__":
    main()