#!/usr/bin/env python3
"""
Daily Readings Mailer (Auto-discovery + Year-agnostic)

What this does
- Recursively finds JSON content files anywhere in the repo:
  - daily-stoic-*.json       (per-month files)
  - daily-dad-*.json         (per-month files)
  - weekly-reflections.json  (single file)
  - daily-journal.json OR thought_readings.json (single file)
- Ignores year: keys are "MM-DD".
- Morning:
  - If today has a weekly entry → include full weekly entry.
  - Else → include a summary of the latest prior weekly entry (wrap to most recent if none prior).
  - Always include FULL Stoic and FULL Dad for EXACT "MM-DD" only (no fallback).
  - Include Journal prompt for EXACT "MM-DD" only (no fallback). Supported fields: "summary" or "text".
- Evening:
  - Summaries only (weekly/stoic/dad). Journal excluded.
- Formatting:
  - Block quotes are italic on a soft card with attribution below.
  - Inside any `content` field, a single `\n` (or `/n`) creates a NEW paragraph.
- SMTP:
  - Uses EMAIL_/SMTP_ secrets. Accepts both legacy and new names:
    EMAIL_FROM, EMAIL_TO_LIST or EMAIL_TO,
    SMTP_HOST or SMTP_SERVER,
    SMTP_PORT, SMTP_USERNAME or EMAIL_USERNAME,
    SMTP_PASSWORD or EMAIL_PASSWORD.
"""

# ===== Imports =====
import os
import re
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

# ===== Defaults =====
DEFAULT_EMAIL_FROM   = "daily.stoic.wisdom.readings@gmail.com"
DEFAULT_EMAIL_TO     = ["steve@thegoodnumbers.com.au"]
DEFAULT_SMTP_HOST    = "smtp.gmail.com"
DEFAULT_SMTP_PORT    = 587
DEFAULT_TZ_OFFSET    = 10  # AEST=10, AEDT=11

# ===== Styling =====
COL_ACCENT    = "#D7DEE5"
COL_TEXT      = "#111111"
COL_H3        = "#153448"
COL_QUOTE_BG  = "#EEF3F7"
COL_QUOTE_BAR = "#BFD3E7"
COL_ATTR      = "#2C3E50"

# ===== Utilities =====
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
    return (datetime.now(timezone.utc) + timedelta(hours=tz_offset)).date()

# ===== Discovery & Loading =====
def find_content_files(root: Path) -> Tuple[List[Path], List[Path], Optional[Path], Optional[Path]]:
    """Return (stoic_files, dad_files, weekly_file, journal_file) discovered recursively."""
    stoic, dad = [], []
    weekly = None
    journal = None
    for p in root.rglob("*.json"):
        name = p.name.lower()
        if name.startswith("daily-stoic-"):
            stoic.append(p)
        elif name.startswith("daily-dad-"):
            dad.append(p)
        elif name == "weekly-reflections.json":
            weekly = p
        elif name == "daily-journal.json" or name == "thought_readings.json":
            journal = p
    stoic.sort(); dad.sort()
    return stoic, dad, weekly, journal

def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON parse error in {path}: {e}")
    except FileNotFoundError:
        return {}
    except Exception as e:
        raise SystemExit(f"Failed reading {path}: {e}")

def merge_monthlies(paths: List[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for p in paths:
        obj = load_json(p)
        merged.update(obj)
    return merged

# ===== Date helpers =====
def latest_on_or_before(target_mmdd: str, keys: List[str]) -> Optional[str]:
    """Return the latest key <= target_mmdd; if none, return the most recent available key; keys are 'MM-DD'."""
    valid = [k for k in keys if re.fullmatch(r"\d{2}-\d{2}", k)]
    valid.sort()
    prior = [k for k in valid if k <= target_mmdd]
    if prior:
        return prior[-1]
    return valid[-1] if valid else None

# ===== Rendering =====
def _split_into_paragraphs(text: str) -> List[str]:
    """Normalize literal '\\n' and '/n' to real newlines, and split on ONE OR MORE newlines -> new paragraphs."""
    if text is None:
        return []
    normalized = text.replace("\\n", "\n").replace("/n", "\n").strip()
    if not normalized:
        return []
    return [p for p in re.split(r"(?:\r?\n)+", normalized) if p.strip()]

def render_blocks(blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for b in (blocks or []):
        typ = (b.get("type") or "").lower()
        content = (b.get("content") or "").strip()
        attribution = (b.get("attribution") or "").strip()
        if not content:
            continue
        if typ == "blockquote":
            # Each paragraph becomes an italic line block inside the card
            spans = "".join([f"<span style='display:block; margin:0 0 10px 0;'>{para}</span>" for para in _split_into_paragraphs(content)])
            q_html = (
                f"<div style='margin:14px 0; background:{COL_QUOTE_BG}; "
                f"border-left:4px solid {COL_QUOTE_BAR}; padding:12px 14px; border-radius:10px;'>"
                f"<em style='display:block;'>{spans}</em>"
                + (f"<div style='text-align:right; margin-top:8px; color:{COL_ATTR};'>— {attribution}</div>" if attribution else "")
                + "</div>"
            )
            parts.append(q_html)
        else:
            paras_html = "".join([
                f"<p style='margin:0 0 14px 0; white-space:normal;'>{para}</p>"
                for para in _split_into_paragraphs(content)
            ])
            parts.append(paras_html)
    return "".join(parts)

def section_html(emoji: str, title: str, body_html: str) -> str:
    return f"<section style='margin:0 0 22px 0;'><h3 style='margin:0 0 10px 0; color:{COL_H3};'>{emoji} {title}</h3>{body_html}</section>"

def build_email_html(subject_h2: str, sections: List[str]) -> str:
    inner = ("<hr style='border:none;border-top:1px solid {0};margin:16px 0;'/>".format(COL_ACCENT)).join(sections)
    return (
        "<html><body style='margin:0;padding:0;background:#ffffff;'>"
        f"<div style='max-width:680px;margin:0 auto;padding:28px;"
        f"font-family:Georgia, \"Times New Roman\", serif; line-height:1.6; color:{COL_TEXT}; font-size:16px;'>"
        f"<h2 style='margin:0 0 18px 0;'>{subject_h2}</h2>{inner}</div></body></html>"
    )

def first_sentence(text: str, max_chars: int = 240) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    for i in range(len(cut)-1, -1, -1):
        if cut[i] in ".!?":
            return cut[:i+1].strip()
    return cut.strip() + "…"

def summarise_entry(entry: Dict[str, Any]) -> str:
    if not entry:
        return ""
    s = (entry.get("summary") or entry.get("text") or "").strip()
    if s:
        return s
    blocks = entry.get("fullText", [])
    for blk in blocks:
        txt = (blk.get("content") or "").strip()
        if txt:
            return first_sentence(txt)
    return ""

# ===== Email sender =====
def send_email(subject: str, html: str, email_from: str, to_list: List[str], smtp_host: str, smtp_port: int, username: str, password: str):
    if not smtp_host:
        raise SystemExit("SMTP host is empty.")
    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(to_list)
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(msg)

# ===== Main =====
def main():
    ap = argparse.ArgumentParser(description="Send Morning Wisdom or Evening Digest emails")
    ap.add_argument("--mode", choices=["morning", "evening"], default="morning")
    ap.add_argument("--date", help="YYYY-MM-DD (defaults to 'today' using TZ_OFFSET)")
    ap.add_argument("--from", dest="sender", default=os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM))
    ap.add_argument("--to", action="append", default=None, help="Recipient (repeatable). If omitted, uses EMAIL_TO_LIST or EMAIL_TO.")
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

    # Discover & load
    root = Path(".").resolve()
    stoic_files, dad_files, weekly_file, journal_file = find_content_files(root)
    stoic_all  = merge_monthlies(stoic_files)
    dad_all    = merge_monthlies(dad_files)
    weekly_all = load_json(weekly_file)
    journal_all= load_json(journal_file)

    # Exact-only for daily sources
    stoic_entry   = stoic_all.get(key_today, {})
    dad_entry     = dad_all.get(key_today, {})
    journal_entry = journal_all.get(key_today, {})  # supports "summary" or "text"

    # Weekly fallback (latest on/before; wrap-around allowed)
    week_entry = {}
    week_key_used = None
    if weekly_all:
        wk_key = latest_on_or_before(key_today, list(weekly_all.keys()))
        if wk_key:
            week_key_used = wk_key
            week_entry = weekly_all.get(wk_key, {})

    # Build email
    sections: List[str] = []
    if args.mode == "morning":
        subject = f"Morning Wisdom — {date_str_long}"

        # Weekly
        if week_entry:
            if week_key_used == key_today:
                sections.append(section_html("📅", "Weekly Reflection", render_blocks(week_entry.get("fullText", []))))
            else:
                wk_sum = summarise_entry(week_entry) or "—"
                note = f"<div style='font-size:12px;opacity:0.8;margin-bottom:6px;'>Using latest weekly entry from {week_key_used}.</div>"
                sections.append(section_html("📅", "Weekly Reflection — Summary", note + f"<p style='margin:0;'>{wk_sum}</p>"))
        else:
            sections.append(section_html("📅", "Weekly Reflection — Summary", "<p>No weekly entries found.</p>"))

        # Stoic (full, exact only)
        if stoic_entry:
            sections.append(section_html("🧘‍♂️", "Daily Stoic", render_blocks(stoic_entry.get("fullText", []))))
        else:
            sections.append(section_html("🧘‍♂️", "Daily Stoic", "<p>—</p>"))

        # Dad (full, exact only)
        if dad_entry:
            sections.append(section_html("👨‍👧", "Daily Dad", render_blocks(dad_entry.get("fullText", []))))
        else:
            sections.append(section_html("👨‍👧", "Daily Dad", "<p>—</p>"))

        # Journal (exact only; summary or text)
        jp = (journal_entry.get("summary") or journal_entry.get("text") or "").strip()
        if jp:
            sections.append(section_html("✍️", "Journal Prompt", f"<p style='margin:0;'>{jp}</p>"))
        else:
            sections.append(section_html("✍️", "Journal Prompt", "<p>—</p>"))

        html = build_email_html(f"Your readings and meditations for {date_str_long}", sections)

    else:
        subject = f"Evening Digest — {date_str_long}"
        def sum_or_dash(e): return summarise_entry(e) if e else "—"
        items = []
        if week_entry:
            items.append(f"<li><strong>Weekly:</strong> {sum_or_dash(week_entry)}</li>")
        else:
            items.append("<li><strong>Weekly:</strong> —</li>")
        items.append(f"<li><strong>Stoic:</strong> {sum_or_dash(stoic_entry)}</li>")
        items.append(f"<li><strong>Dad:</strong> {sum_or_dash(dad_entry)}</li>")
        digest_html = "<ul style='margin:0 0 0 20px; padding:0 0 0 6px;'>" + "".join(items) + "</ul>"
        html = build_email_html(f"A quick evening summary for {date_str_long}", [digest_html])

    # Send
    send_email(subject, html, args.sender, to_list, args.smtp_host, args.smtp_port, args.smtp_user, args.smtp_pass)
    print(f"Sent: {subject} -> {', '.join(to_list)}")

if __name__ == "__main__":
    main()
