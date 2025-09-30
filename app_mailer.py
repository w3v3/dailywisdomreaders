#!/usr/bin/env python3
"""
Daily Readings Mailer (Clean Rewrite)
-------------------------------------
Supports:
- Stoic & Dad readings in per-month JSON files (daily-stoic-*.json, daily-dad-*.json).
- Weekly reflections in one JSON file.
- Daily journal in one JSON file.
- Morning mode: full weekly (if today) else AI-style summary of latest weekly; full stoic; full dad; include journal prompt.
- Evening mode: summaries only (weekly/stoic/dad), exclude journal.
Formatting:
- Block quotes get italic text and a soft background "card", attribution separated beneath.
"""
import os, smtplib, argparse, json
from glob import glob
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

# ---------- Defaults (override with ENV or CLI) ----------
DEFAULT_STOIC_GLOB   = "daily-stoic-*.json"      # per-month files, e.g., daily-stoic-01.json
DEFAULT_DAD_GLOB     = "daily-dad-*.json"        # per-month files, e.g., daily-dad-01.json
DEFAULT_WEEKLY_FILE  = "weekly-reflections.json" # single file
DEFAULT_JOURNAL_FILE = "daily-journal.json"      # single file

DEFAULT_EMAIL_FROM   = "daily.stoic.wisdom.readings@gmail.com"
DEFAULT_EMAIL_TO     = ["steve@thegoodnumbers.com.au"]
DEFAULT_SMTP_HOST    = "smtp.gmail.com"
DEFAULT_SMTP_PORT    = 587
DEFAULT_TZ_OFFSET    = 10  # AEST = 10, AEDT = 11

# ---------- Styling ----------
COL_BG_SOFT   = "#F5F7F9"
COL_ACCENT    = "#D7DEE5"
COL_TEXT      = "#111111"
COL_H3        = "#153448"
COL_QUOTE_BG  = "#EEF3F7"
COL_QUOTE_BAR = "#BFD3E7"
COL_ATTR      = "#2C3E50"

def today_local_date(tz_offset: int) -> datetime.date:
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=tz_offset)).date()

def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON parse error in {path}: {e}")

def merge_monthlies(pattern: str) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for p in sorted(glob(pattern)):
        obj = load_json(p)
        merged.update(obj)
    return merged

def first_sentence(text: str, max_chars: int = 280) -> str:
    t = (text or "").strip()
    if not t: return ""
    # Try to end at sentence boundary before max_chars
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    m = re.search(r'[.!?](?=[^.!?]*$)', cut)
    if m:
        end = m.end()
        return cut[:end].strip()
    return cut.strip() + "…"

def summarise_entry(entry: Dict[str, Any]) -> str:
    # Prefer provided "summary" if present
    s = (entry or {}).get("summary", "").strip()
    if s:
        return s
    # Else derive from first paragraph/blockquote content
    blocks = (entry or {}).get("fullText", [])
    for blk in blocks:
        txt = (blk.get("content") or "").strip()
        if txt:
            return first_sentence(txt, 240)
    return ""

def render_blocks(blocks: List[Dict[str, Any]]) -> str:
    """Render fullText array: paragraphs normal; blockquotes with italic/background and separate attribution."""
    parts: List[str] = []
    for b in blocks or []:
        typ = (b.get("type") or "").lower()
        content = (b.get("content") or "").strip()
        attribution = (b.get("attribution") or "").strip()
        if not content:
            continue
        if typ == "blockquote":
            q_html = (
                f"<div style='margin:14px 0; background:{COL_QUOTE_BG}; "
                f"border-left:4px solid {COL_QUOTE_BAR}; padding:12px 14px; border-radius:10px;'>"
                f"<em style='display:block; white-space:pre-wrap;'>{content}</em>"
                + (f"<div style='text-align:right; margin-top:8px; color:{COL_ATTR};'>— {attribution}</div>" if attribution else "")
                + "</div>"
            )
            parts.append(q_html)
        else:
            parts.append(f"<p style='margin:0 0 14px 0; white-space:pre-wrap;'>{content}</p>")
    return "\n".join(parts)

def section_html(emoji: str, title: str, body_html: str) -> str:
    return (
        f"<section style='margin:0 0 22px 0;'>"
        f"<h3 style='margin:0 0 10px 0; color:{COL_H3};'>{emoji} {title}</h3>"
        f"{body_html}"
        f"</section>"
    )

def build_email_html(subject_h2: str, sections: List[str]) -> str:
    inner = "\n<hr style='border:none;border-top:1px solid {0};margin:16px 0;'/>\\n".format(COL_ACCENT).join(sections)
    return (
        "<html><body style='margin:0;padding:0;background:#ffffff;'>"
        f"<div style='max-width:680px;margin:0 auto;padding:28px;"
        f"font-family:Georgia, \"Times New Roman\", serif; line-height:1.6; color:{COL_TEXT}; font-size:16px;'>"
        f"<h2 style='margin:0 0 18px 0;'>{subject_h2}</h2>"
        f"{inner}"
        "</div></body></html>"
    )

def choose_week_for_date(mmdd: str, weekly: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return exact week's entry if exists else None."""
    return weekly.get(mmdd)

def latest_week_before(mmdd: str, weekly: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find the latest weekly entry key <= mmdd (string MM-DD)."""
    keys = sorted(k for k in weekly.keys() if re.fullmatch(r"\d{2}-\d{2}", k))
    for k in reversed(keys):
        if k <= mmdd:
            return weekly.get(k)
    return None

def send_email(subject: str, html: str, email_from: str, to_list: List[str], smtp_host: str, smtp_port: int, username: str, password: str):
    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = ", ".join(to_list)
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(msg)

def main():
    ap = argparse.ArgumentParser(description="Send Morning Wisdom or Evening Digest emails from JSON sources.")
    ap.add_argument("--mode", choices=["morning","evening"], default="morning")
    ap.add_argument("--date", help="YYYY-MM-DD (defaults to 'today' in TZ_OFFSET)")
    ap.add_argument("--stoic-glob", default=os.getenv("STOIC_GLOB", DEFAULT_STOIC_GLOB))
    ap.add_argument("--dad-glob", default=os.getenv("DAD_GLOB", DEFAULT_DAD_GLOB))
    ap.add_argument("--weekly", default=os.getenv("WEEKLY_FILE", DEFAULT_WEEKLY_FILE))
    ap.add_argument("--journal", default=os.getenv("JOURNAL_FILE", DEFAULT_JOURNAL_FILE))
    ap.add_argument("--from", dest="sender", default=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM))
    ap.add_argument("--to", action="append", default=None, help="Add recipient; can be repeated")
    ap.add_argument("--smtp-host", default=os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST))
    ap.add_argument("--smtp-port", type=int, default=int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))))
    ap.add_argument("--smtp-user", default=os.getenv("SMTP_USERNAME", ""))
    ap.add_argument("--smtp-pass", default=os.getenv("SMTP_PASSWORD", ""))
    ap.add_argument("--tz-offset", type=int, default=int(os.getenv("TZ_OFFSET", str(DEFAULT_TZ_OFFSET))))
    args = ap.parse_args()

    # Resolve recipients
    to_list = args.to
    if to_list is None:
        env_list = os.getenv("EMAIL_TO_LIST", "")
        to_list = [x.strip() for x in env_list.split(",") if x.strip()] or DEFAULT_EMAIL_TO

    # Resolve date & key
    if args.date:
        ref = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        ref = today_local_date(args.tz_offset)
    mmdd = f"{ref.month:02d}-{ref.day:02d}"

    # Load data
    stoic_all  = merge_monthlies(args.stoic_glob)
    dad_all    = merge_monthlies(args.dad_glob)
    weekly_all = load_json(args.weekly)
    journal_all= load_json(args.journal)

    stoic_today  = stoic_all.get(mmdd, {})
    dad_today    = dad_all.get(mmdd, {})
    weekly_today = choose_week_for_date(mmdd, weekly_all)

    # MORNING vs EVENING
    date_str_long = ref.strftime("%A, %B %d, %Y")
    if args.mode == "morning":
        subject = f"Morning Wisdom — {date_str_long}"

        sections: List[str] = []

        # Weekly (full today OR AI summary of latest prior)
        if weekly_today:
            weekly_html = render_blocks(weekly_today.get("fullText", []))
            sections.append(section_html("📅", "Weekly Reflection", weekly_html))
        else:
            latest = latest_week_before(mmdd, weekly_all)
            if latest:
                ai = summarise_entry(latest)
                ai_html = f"<p style='margin:0;'>{ai}</p>"
            else:
                ai_html = "<p style='margin:0;'>No weekly entry found yet.</p>"
            sections.append(section_html("📅", "Weekly Reflection — Summary", ai_html))

        # Stoic (full)
        if stoic_today:
            stoic_html = render_blocks(stoic_today.get("fullText", []))
            sections.append(section_html("🧘‍♂️", "Daily Stoic", stoic_html))
        else:
            sections.append(section_html("🧘‍♂️", "Daily Stoic", "<p>No entry for today.</p>"))

        # Dad (full)
        if dad_today:
            dad_html = render_blocks(dad_today.get("fullText", []))
            sections.append(section_html("👨‍👧", "Daily Dad", dad_html))
        else:
            sections.append(section_html("👨‍👧", "Daily Dad", "<p>No entry for today.</p>"))

        # Journal (prompt only)
        journal_today = journal_all.get(mmdd, {})
        if journal_today:
            prompt = (journal_today.get("summary") or "").strip()
            j_html = f"<p style='margin:0;'>{prompt}</p>" if prompt else "<p style='margin:0;'>—</p>"
            sections.append(section_html("✍️", "Journal Prompt", j_html))

        html = build_email_html(f"Your readings and meditations for {date_str_long}", sections)

    else:  # EVENING digest — summaries only, exclude journal
        subject = f"Evening Digest — {date_str_long}"
        items: List[str] = []

        # Weekly summary
        if weekly_today:
            wk_sum = summarise_entry(weekly_today)
        else:
            latest = latest_week_before(mmdd, weekly_all)
            wk_sum = summarise_entry(latest) if latest else "No weekly entry found yet."
        items.append(f"<li><strong>Weekly:</strong> {wk_sum}</li>")

        # Stoic summary
        st_sum = summarise_entry(stoic_today) if stoic_today else "—"
        items.append(f"<li><strong>Stoic:</strong> {st_sum}</li>")

        # Dad summary
        dd_sum = summarise_entry(dad_today) if dad_today else "—"
        items.append(f"<li><strong>Dad:</strong> {dd_sum}</li>")

        digest_html = "<ul style='margin:0 0 0 20px; padding:0 0 0 6px;'>\n" + "\n".join(items) + "\n</ul>"
        html = build_email_html(f"A quick evening summary for {date_str_long}", [digest_html])

    # Send
    send_email(subject, html, args.sender, to_list, args.smtp_host, args.smtp_port, args.smtp_user, args.smtp_pass)
    print(f"Sent: {subject} -> {', '.join(to_list)}")

if __name__ == "__main__":
    main()