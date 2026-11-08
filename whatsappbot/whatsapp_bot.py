import argparse, csv, re, sys, time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "wa_profile"
OUT = ROOT / "output"

def start(p):
    PROFILE.mkdir(exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=False,
        viewport={"width": 1365, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
    input("Scan the WhatsApp Web QR code if needed. When chats are visible, press ENTER...")
    return ctx, page

def open_chat(page, name):
    candidates = [
        page.get_by_role("textbox", name=re.compile("Search", re.I)),
        page.locator('div[contenteditable="true"][data-tab="3"]'),
        page.locator('div[contenteditable="true"]').first
    ]
    search = None
    for loc in candidates:
        try:
            if loc.count() and loc.first.is_visible():
                search = loc.first
                break
        except Exception:
            pass
    if search is None:
        raise RuntimeError("Chat search box not found; WhatsApp may have changed its layout.")
    search.click()
    try:
        search.fill(name)
    except Exception:
        search.press("Control+A")
        search.type(name, delay=50)
    page.wait_for_timeout(1800)
    try:
        page.get_by_text(name, exact=True).first.click(timeout=5000)
    except PlaywrightTimeoutError:
        raise RuntimeError(f"Could not find chat '{name}'. Check the exact visible chat name.")
    page.wait_for_timeout(900)

def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or not {"name", "message", "consent"}.issubset(rows[0]):
        raise ValueError("CSV requires columns: name,message,consent")
    return rows

def send(page, path, enabled, delay):
    rows = [r for r in read_csv(path)
            if r["name"].strip() and r["message"].strip()
            and r["consent"].strip().lower() in ("yes", "true", "1")]
    print(f"\nEligible opted-in contacts: {len(rows)}")
    for r in rows:
        print(f"- {r['name']}: {r['message']}")
    if not enabled:
        print("\nDRY RUN: nothing sent. Review, then rerun with --send.")
        return
    phrase = f"SEND {len(rows)}"
    if input(f"\nType '{phrase}' to confirm: ").strip() != phrase:
        print("Confirmation mismatch. Nothing sent.")
        return
    results = []
    for i, r in enumerate(rows):
        status, detail = "failed", ""
        try:
            open_chat(page, r["name"].strip())
            composer = page.locator("footer div[contenteditable='true']").last
            if not composer.count():
                composer = page.locator("div[contenteditable='true']").last
            composer.click()
            composer.fill(r["message"].strip())
            composer.press("Enter")
            page.wait_for_timeout(700)
            status, detail = "submitted", "Submitted in WhatsApp Web"
            print(f"[{i+1}/{len(rows)}] Submitted to {r['name']}")
        except Exception as e:
            detail = str(e)
            print(f"Failed for {r['name']}: {detail}")
        results.append({"timestamp": datetime.now().isoformat(timespec="seconds"),
                        "name": r["name"], "status": status, "detail": detail})
        if i < len(rows)-1:
            time.sleep(max(5, delay))
    OUT.mkdir(exist_ok=True)
    target = OUT / f"send_results_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with target.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp","name","status","detail"])
        w.writeheader(); w.writerows(results)
    print("Results:", target)

def extract(page, chat, keywords):
    open_chat(page, chat)
    terms = [x.strip().lower() for x in keywords.split(",") if x.strip()]
    nodes = page.locator('[data-testid="msg-container"]')
    rows = []
    for i in range(nodes.count()):
        try:
            value = nodes.nth(i).inner_text(timeout=1500).strip()
        except Exception:
            continue
        hits = [k for k in terms if k in value.lower()]
        if value and (not terms or hits):
            rows.append({"chat": chat, "message_text": value,
                         "matched_keywords": ", ".join(hits)})
    OUT.mkdir(exist_ok=True)
    target = OUT / f"chat_extract_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with target.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["chat","message_text","matched_keywords"])
        w.writeheader(); w.writerows(rows)
    print(f"Extracted {len(rows)} visible messages. Saved: {target}")
    print("Only currently rendered messages are captured; older history may need manual scrolling.")

def main():
    ap = argparse.ArgumentParser(description="Consent-based WhatsApp Web automation starter")
    sub = ap.add_subparsers(dest="mode", required=True)
    sp = sub.add_parser("send")
    sp.add_argument("--csv", default="data/contacts.csv")
    sp.add_argument("--send", action="store_true", help="Enable sending after preview and typed confirmation")
    sp.add_argument("--delay", type=int, default=8)
    ep = sub.add_parser("extract")
    ep.add_argument("--chat", required=True)
    ep.add_argument("--keywords", default="")
    args = ap.parse_args()
    csv_path = Path(args.csv)
    if args.mode == "send" and not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    with sync_playwright() as p:
        ctx, page = start(p)
        try:
            if args.mode == "send":
                send(page, csv_path, args.send, args.delay)
            else:
                extract(page, args.chat, args.keywords)
        finally:
            input("Press ENTER to close Chromium...")
            ctx.close()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: sys.exit(130)
