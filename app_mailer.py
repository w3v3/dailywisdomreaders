#!/usr/bin/env python3
"""
Daily Readings Mailer (Auto-discovery + Year-agnostic)
------------------------------------------------------
- Automatically finds JSON content files anywhere under the repo (no path/glob secrets needed).
- Ignores year; uses "MM-DD" keys across all files.
- For missing daily keys, falls back to the latest prior date key in the year; if none prior, wraps to the highest available key.
- Weekly: morning uses full if today else latest prior summary; evening uses summaries; same fallback.
- Journal: morning shows today's prompt if present, else latest prior; evening excludes.
- Uses existing SMTP/EMAIL secrets: EMAIL_FROM, EMAIL_TO_LIST or EMAIL_TO, SMTP_HOST/SMTP_SERVER, SMTP_PORT, SMTP_USERNAME/EMAIL_USERNAME, SMTP_PASSWORD/EMAIL_PASSWORD.
"""
import os, smtplib, argparse, json
from pathlib import Path
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

# ---------- Defaults ----------
DEFAULT_EMAIL_FROM   = "daily.stoic.wisdom.readings@gmail.com"
DEFAULT_EMAIL_TO     = ["steve@thegoodnumbers.com.au"]
DEFAULT_SMTP_HOST    = "smtp.gmail.com"
DEFAULT_SMTP_PORT    = 587
DEFAULT_TZ_OFFSET    = 10  # AEST=10, AEDT=11

# ---------- Styling ----------
COL_BG_SOFT   = "#F5F7F9"
COL_ACCENT    = "#D7DEE5"
COL_TEXT      = "#111111"
COL_H3        = "#153448"
COL_QUOTE_BG  = "#EEF3F7"
COL_QUOTE_BAR = "#BFD3E7"
COL_ATTR      = "#2C3E50"

def env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    try:
        return int(v) if v is not None and str(v).strip() != '' else default
    except (TypeError, ValueError):
        return default

def env_list_email() -> List[str]:
    raw = os.getenv("EMAIL_TO_LIST", "") or os.getenv("EMAIL_TO", "")
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items or DEFAULT_EMAIL_TO

def local_today(tz_offset: int) -> datetime.date:
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=tz_offset)).date()

# --------- File auto-discovery ---------
def find_content_files(root: Path) -> Tuple[List[Path], List[Path], Optional[Path], Optional[Path]]:
    """Return (stoic_files, dad_files, weekly_file, journal_file) discovered recursively."""
    stoic, dad = [], []
    weekly = None
    journal = None
    for p in root.rglob("*.json"):
        name = p.name.lower()
        if name.startswith("daily-stoic-") and name.endswith(".json"):
            stoic.append(p)
        elif name.startswith("daily-dad-") and name.endswith(".json"):
            dad.append(p)
        elif name == "weekly-reflections.json":
            weekly = p
        elif name == "daily-journal.json":
            journal = p
    stoic.sort()
    dad.sort()
    return stoic, dad, weekly, journal

def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON parse error in {path}: {e}")

def merge_monthlies(paths: List[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for p in paths:
        obj = load_json(p)
        merged.update(obj)
    return merged

# --------- Date helpers (year-agnostic) ---------
def mmdd(date_obj: datetime.date) -> str:
    return f"{date_obj.month:02d}-{date_obj.day:02d}"

def latest_on_or_before(target_mmdd: str, keys: List[str]) -> Optional[str]:
    keys_sorted = sorted([k for k in keys if re.fullmatch(r"\d{2}-\d{2}", k)])
    prior = [k for k in keys_sorted if k <= target_mmdd]
    if prior:
        return prior[-1]
    return keys_sorted[-1] if keys_sorted else None  # wrap-around to latest available

# --------- Rendering helpers ---------
def render_blocks(blocks: List[Dict[str, Any]]) -> str:
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

def first_sentence(text: str, max_chars: int = 240) -> str:
    t = (text or "").strip()
    if not t: return ""
    if len(t) <= max_chars: return t
    cut = t[:max_chars]
    # try break at last sentence end
    for i in range(len(cut)-1, -1, -1):
        if cut[i] in ".!?":
            return cut[:i+1].strip()
    return cut.strip() + "…"

def summarise_entry(entry: Dict[str, Any]) -> str:
    if not entry: return ""
    s = (entry.get("summary") or "").strip()
    if s: return s
    blocks = entry.get("fullText", [])
    for blk in blocks:
        txt = (blk.get("content") or "").strip()
        if txt: return first_sentence(txt)
    return ""

# --------- Email ---------
def send_email(subject: str, html: str, email_from: str, to_list: List[str], smtp_host: str, smtp_port: int, username: str, password: str):
    if not smtp_host:
        raise SystemExit("SMTP host is empty. Set SMTP_HOST or SMTP_SERVER secret.")
    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(to_list)
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(msg)

# --------- Main ---------
def main():
    ap = argparse.ArgumentParser(description="Send Morning Wisdom or Evening Digest emails from discovered JSON sources.")
    ap.add_argument("--mode", choices=["morning","evening"], default="morning")
    ap.add_argument("--date", help="YYYY-MM-DD (defaults to 'today' using TZ_OFFSET)")
    ap.add_argument("--from", dest="sender", default=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM))
    ap.add_argument("--to", action="append", default=None, help="Recipient (can repeat). If not provided, uses EMAIL_TO_LIST/EMAIL_TO.")
    ap.add_argument("--smtp-host", default=os.getenv("SMTP_HOST", os.getenv("SMTP_SERVER", DEFAULT_SMTP_HOST)))
    ap.add_argument("--smtp-port", type=int, default=env_int("SMTP_PORT", DEFAULT_SMTP_PORT))
    ap.add_argument("--smtp-user", default=os.getenv("SMTP_USERNAME", os.getenv("EMAIL_USERNAME", "")))
    ap.add_argument("--smtp-pass", default=os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", "")))
    ap.add_argument("--tz-offset", type=int, default=env_int("TZ_OFFSET", DEFAULT_TZ_OFFSET))
    args = ap.parse_args()

    # Date
    if args.date:
        try:
            ref = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("Invalid --date; use YYYY-MM-DD")
    else:
        ref = local_today(args.tz_offset)
    key_today = f"{ref.month:02d}-{ref.day:02d}"
    date_str_long = ref.strftime("%A, %B %d, %Y")

    # Recipients
    to_list = args.to or env_list_email()

    # Discover content
    root = Path(".").resolve()
    stoic_files, dad_files, weekly_file, journal_file = find_content_files(root)
    stoic_all  = merge_monthlies(stoic_files)
    dad_all    = merge_monthlies(dad_files)
    weekly_all = load_json(weekly_file) if weekly_file else {}
    journal_all= load_json(journal_file) if journal_file else {}

    # Fetch daily entries with fallback
    def get_with_fallback(all_entries: Dict[str, Any], mmdd_key: str) -> Tuple[Dict[str, Any], Optional[str]]:
        if mmdd_key in all_entries:
            return all_entries[mmdd_key], mmdd_key
        fallback_key = latest_on_or_before(mmdd_key, list(all_entries.keys()))
        return (all_entries.get(fallback_key, {}), fallback_key)

    stoic_entry, stoic_key   = get_with_fallback(stoic_all, key_today)
    dad_entry, dad_key       = get_with_fallback(dad_all, key_today)
    week_entry, week_key     = get_with_fallback(weekly_all, key_today)
    journal_entry, j_key     = get_with_fallback(journal_all, key_today)

    # Build email per mode
    sections: List[str] = []
    if args.mode == "morning":
        subject = f"Morning Wisdom — {date_str_long}"
        # Weekly: full if today's key matches; else summary of latest prior (wrap-around allowed)
        if week_entry and week_key == key_today:
            w_html = render_blocks(week_entry.get("fullText", []))
            sections.append(section_html("📅", "Weekly Reflection", w_html))
        elif week_entry:
            wk_sum = summarise_entry(week_entry) or "—"
            note = f"<div style='font-size:12px;opacity:0.8;margin-bottom:6px;'>Using latest weekly entry from {week_key}.</div>"
            sections.append(section_html("📅", "Weekly Reflection — Summary", note + f"<p style='margin:0;'>{wk_sum}</p>"))
        else:
            sections.append(section_html("📅", "Weekly Reflection — Summary", "<p>No weekly entries found.</p>"))

        # Stoic full (fallback OK)
        if stoic_entry:
            if stoic_key and stoic_key != key_today:
                note = f"<div style='font-size:12px;opacity:0.8;margin-bottom:6px;'>Using nearest entry from {stoic_key}.</div>"
            else:
                note = ""
            sections.append(section_html("🧘‍♂️", "Daily Stoic", note + render_blocks(stoic_entry.get("fullText", []))))
        else:
            sections.append(section_html("🧘‍♂️", "Daily Stoic", "<p>No entries found.</p>"))

        # Dad full (fallback OK)
        if dad_entry:
            if dad_key and dad_key != key_today:
                note = f"<div style='font-size:12px;opacity:0.8;margin-bottom:6px;'>Using nearest entry from {dad_key}.</div>"
            else:
                note = ""
            sections.append(section_html("👨‍👧", "Daily Dad", note + render_blocks(dad_entry.get("fullText", []))))
        else:
            sections.append(section_html("👨‍👧", "Daily Dad", "<p>No entries found.</p>"))

        # Journal prompt (fallback OK)
        if journal_entry:
            prompt = (journal_entry.get("summary") or "").strip()
            if prompt:
                pref = f"<div style='font-size:12px;opacity:0.8;margin-bottom:6px;'>Using prompt from {j_key}.</div>" if j_key and j_key != key_today else ""
                sections.append(section_html("✍️", "Journal Prompt", pref + f"<p style='margin:0;'>{prompt}</p>"))
            else:
                sections.append(section_html("✍️", "Journal Prompt", "<p>—</p>"))
        else:
            sections.append(section_html("✍️", "Journal Prompt", "<p>—</p>"))

        html = build_email_html(f"Your readings and meditations for {date_str_long}", sections)

    else:  # evening digest
        subject = f"Evening Digest — {date_str_long}"
        items: List[str] = []
        def sum_or_dash(e): return summarise_entry(e) if e else "—"
        # Weekly: summary (fallback OK)
        if week_entry:
            wk_sum = sum_or_dash(week_entry)
            items.append(f"<li><strong>Weekly:</strong> {wk_sum}</li>")
        else:
            items.append("<li><strong>Weekly:</strong> —</li>")
        # Stoic
        items.append(f"<li><strong>Stoic:</strong> {sum_or_dash(stoic_entry)}</li>")
        # Dad
        items.append(f"<li><strong>Dad:</strong> {sum_or_dash(dad_entry)}</li>")
        digest_html = "<ul style='margin:0 0 0 20px; padding:0 0 0 6px;'>\n" + "\n".join(items) + "\n</ul>"
        html = build_email_html(f"A quick evening summary for {date_str_long}", [digest_html])

    # Send
    send_email(subject, html, args.sender, to_list, args.smtp_host, args.smtp_port, args.smtp_user, args.smtp_pass)
    print(f"Sent: {subject} -> {', '.join(to_list)}")

if __name__ == "__main__":
    main()