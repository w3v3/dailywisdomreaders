#!/usr/bin/env python3
import csv
import re
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from typing import Optional
from wordfreq import zipf_frequency

# ========= CONFIG =========
CSV_PATH       = "Readings.csv"  # Date as DD/MM/YYYY
EMAIL_FROM     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_TO       = "steve@thegoodnumbers.com.au, readlater.dggtboab4vm@instapaper.com"
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_USER     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_PASS     = "ohov qtwt gnar sxwb"  # Gmail App Password if 2FA enabled
# =========================

# --- helpers for cautious title-casing (protect acronyms) ---
ACRONYMS = {"UCLA","NASA","AI","SQL","USA","UK","EU"}  # extend as needed

def looks_like_acronym(s: str) -> bool:
    return s.isupper() and s in ACRONYMS

def smart_title_token(tok: str) -> str:
    if looks_like_acronym(tok):
        return tok
    if zipf_frequency(tok.lower(), 'en') >= 2.5 or len(tok) >= 5:
        return tok[:1].upper() + tok[1:].lower()
    return tok

def smart_title_case(line: str) -> str:
    return re.sub(r"[A-Za-z]+", lambda m: smart_title_token(m.group(0)), line)

# --- proper-name normalizer for Stoic philosophers (handles stray internal spaces) ---
CANONICAL_NAMES = [
    "Marcus Aurelius", "Aurelius", "Marcus",
    "Seneca", "Epictetus", "Zeno", "Cleanthes", "Chrysippus",
    "Musonius Rufus", "Musonius", "Rufus",
    "Antoninus Pius", "Antoninus", "Pius",
    "Hierocles", "Cato", "Diogenes",
]

def make_spaceless_pattern(name: str) -> re.Pattern:
    tokens = name.split()
    token_patterns = []
    for tok in tokens:
        chars = list(tok)
        token_patterns.append(r"\s*".join(map(re.escape, chars)))
    full = r"\b" + r"\s+".join(token_patterns) + r"\b"
    return re.compile(full, flags=re.IGNORECASE)

NAME_PATTERNS = [(make_spaceless_pattern(n), n) for n in CANONICAL_NAMES]

def fix_proper_names(t: str) -> str:
    for pat, canon in NAME_PATTERNS:
        t = pat.sub(canon, t)
    return t

# --- main cleaner: additive fixes, word-aware ---
def clean_text_block(text: str) -> str:
    t = (text or "").strip()

    # Merge stray leading letter + word ONLY if the join is a common English word.
    def merge_if_word(m):
        cand = (m.group(1) + m.group(2)).lower()
        return m.group(1)+m.group(2) if zipf_frequency(cand, 'en') >= 3.0 else m.group(0)
    t = re.sub(r'\b([A-Z])\s+([A-Za-z]{2,})', merge_if_word, t)

    # Normalize whitespace
    t = re.sub(r'\s+', ' ', t)

    # Ahome/Akind/Akid’s -> A home/A kind/A kid’s (but keep Another/Already/etc.)
    def split_after_A(m):
        word  = m.group(1)
        combo = ('a' + re.sub(r"[’']", "", word)).lower()
        return 'A ' + word if zipf_frequency(combo, 'en') < 3.0 else 'A' + word
    t = re.sub(r'\bA([a-z][a-z]+(?:’s|\'s)?)\b', split_after_A, t)

    # A t -> At, A n -> An
    t = re.sub(r'\bA\s+t\b', 'At', t)
    t = re.sub(r'\bA\s+n\b', 'An', t)

    # Isee/Ithink -> I see/I think (only if following is common)
    def split_after_I(m):
        word = m.group(1)
        return 'I ' + word if zipf_frequency(word.lower(), 'en') >= 3.0 else 'I' + word
    t = re.sub(r'\bI([a-z]{2,})\b', split_after_I, t)

    # Em-dash attribution line tidy
    if t.startswith('—'):
        core = t.lstrip('—').strip()
        core = re.sub(r'\s+,', ',', core)
        t = '— ' + smart_title_case(core)

    # ALL-CAPS -> cautious token title-case (preserve acronyms)
    if t and t.upper() == t and any(c.isalpha() for c in t):
        t = smart_title_case(t)

    # Normalize Stoic names with stray internal spaces/case
    t = fix_proper_names(t)

    return t

# --- Quote handling: italicize quote only, keep attribution normal; indent quote text only is grey ---
QUOTE_WITH_ATTR_RE = re.compile(
    r'^\s*([“"][^"”]+[”"])\s*(?:([—–-]\s*[A-Z][A-Za-z0-9 .,’\'–—\-,:;()]+))?\s*$'
)

def render_para_quote_smart(para: str) -> str:
    """
    If paragraph begins with a feature quote, italicize ONLY the quote, keep attribution normal.
    Indent the whole line slightly, but grey color applies only to the quote span.
    """
    cleaned = clean_text_block(para)
    m = QUOTE_WITH_ATTR_RE.match(cleaned)
    if m:
        q = m.group(1).strip()
        a = (m.group(2) or "").strip()
        # indent paragraph; quote text grey + italic; attribution normal color
        if a:
            return (
                '<p style="margin-left:16px;">'
                f'<span style="color:#555;"><em>{q}</em></span> {a}'
                '</p>'
            )
        else:
            return (
                '<p style="margin-left:16px;">'
                f'<span style="color:#555;"><em>{q}</em></span>'
                '</p>'
            )
    return f'<p>{cleaned}</p>'

def section_html(emoji: str, heading: str, raw: str) -> str:
    html = [f'<h3 style="margin:0 0 0.3em 0">{emoji} {heading}</h3>']
    lines = [ln for ln in (raw or "").splitlines() if ln.strip()]

    if lines:
        html.append(f'<p><strong>{clean_text_block(lines[0])}</strong></p>')
    if len(lines) >= 2:
        html.append(f'<p><em>{clean_text_block(lines[1])}</em></p>')

    rest = "\n\n".join(lines[2:]) if len(lines) > 2 else ""
    for para in re.split(r'\n{2,}', rest):
        para = para.strip()
        if not para:
            continue
        html.append(render_para_quote_smart(para))

    return "\n".join(html)

# --- Weekly-only: relax line breaks + quote paragraphization + 'I t' fix ---
def relax_week_text(raw: str):
    if not raw:
        return "", "", ""

    orig_lines = raw.splitlines()
    idxs = [i for i,ln in enumerate(orig_lines) if ln.strip()]
    if not idxs:
        return "", "", ""
    i1 = idxs[0]
    head1 = orig_lines[i1].strip()
    head2 = orig_lines[idxs[1]].strip() if len(idxs) > 1 else ""

    start_body = (idxs[1] + 1) if len(idxs) > 1 else (i1 + 1)
    body = "\n".join(orig_lines[start_body:])

    if body:
        body = re.sub(r'(?<!\n)\n(?!\n)', ' ', body)   # single \n -> space
        body = re.sub(r'\n{3,}', '\n\n', body)        # 3+ \n -> 2

        # Weekly-only OCR artifacts
        body = re.sub(r'\bI\s+t\b', 'It', body)
        body = re.sub(r"(?:\bI\s+t)(’s|'s)\b", r"It\1", body)

        # Separate feature quotes into their own paragraphs
        quote_attr = re.compile(r'(["“][^"”]+["”])\s*((?:—|–|-)\s*[A-Z][A-Za-z0-9 .,’\'–—\-,:;()]+)')
        body = quote_attr.sub(lambda m: f'\n\n{m.group(1)} {m.group(2)}\n\n', body)
        body = re.sub(r'\n{3,}', '\n\n', body).strip()

    return head1, head2, body

def weekly_html(emoji: str, heading: str, raw: str) -> str:
    head1, head2, body = relax_week_text(raw)
    html = [f'<h3 style="margin:0 0 0.3em 0">{emoji} {heading}</h3>']
    if head1:
        html.append(f'<p><strong>{clean_text_block(head1)}</strong></p>')
    if head2:
        html.append(f'<p><em>{clean_text_block(head2)}</em></p>')
    if body:
        for para in re.split(r'\n{2,}', body):
            para = para.strip()
            if not para:
                continue
            html.append(render_para_quote_smart(para))
    return "\n".join(html)

def send_email(override_date: Optional[str] = None):
    # AEST date
    if override_date:
        try:
            ref = datetime.strptime(override_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid --date; use YYYY-MM-DD")
            return
    else:
        now_utc = datetime.now(timezone.utc)
        ref = (now_utc + timedelta(hours=10)).date()

    mmdd = (ref.month, ref.day)

    # Find row by month/day
    today_row = None
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            parts = r.get("Date", "").split("/")
            if len(parts) != 3:
                continue
            try:
                d, m, y = map(int, parts)
            except ValueError:
                continue
            if (m, d) == mmdd:
                today_row = r
                break

    if not today_row or not today_row.get("Daily Stoic", "").strip():
        print(f"No daily entry for {ref.strftime('%d/%m/%Y')}")
        return

    # Fields
    stoic_raw   = today_row.get("Daily Stoic", "")
    dad_raw     = today_row.get("Daily Dad", "")
    thought_raw = today_row.get("Todays Thought", "")
    week_raw    = today_row.get("Week", "").strip()

    # Subject & header
    subject     = ref.strftime("Daily Reflection – %A, %B %d, %Y")
    header_html = f'<h2 style="margin:0 0 0.75em 0">These are your readings and meditations for {ref.strftime("%A, %B %d, %Y")}</h2>'

    # Assemble
    parts = []
    if week_raw:
        parts.append(weekly_html("📅", "Weekly Reflection", week_raw))
        parts.append("<hr/>")

    parts.append(section_html("🧘‍♂️", "Daily Stoic", stoic_raw))
    parts.append("<hr/>")
    parts.append(section_html("👨‍👧", "Daily Dad",   dad_raw))
    parts.append("<hr/>")
    parts.append(section_html("✍️",   "Today’s Thought", thought_raw))

    if parts and parts[-1] == "<hr/>":
        parts.pop()

    # Gentle centered wrapper with modest side padding
    body_html = (
        "<html><body style='margin:0;padding:0;background:#ffffff;'>"
        "<div style='max-width:740px;margin:0 auto;padding:0 18px;"
        "font-family:sans-serif;line-height:1.5;color:#111;'>"
        + header_html + "\n"
        + "\n".join(parts) +
        "</div></body></html>"
    )

    # Send
    msg = MIMEText(body_html, "html")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print("Failed to send email:", e)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Override date (YYYY-MM-DD)", default=None)
    args = p.parse_args()
    send_email(args.date)
