#!/usr/bin/env python3
import csv, re, smtplib, argparse
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from wordfreq import zipf_frequency

# — CONFIGURATION —
CSV_PATH       = "Readings.csv"
EMAIL_FROM     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_TO       = "steve@thegoodnumbers.com.au"
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_USER     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_PASS     = "ohov qtwt gnar sxwb"
# ——————

def is_english_word(w, min_freq=3.0):
    return zipf_frequency(w.lower(), 'en') >= min_freq

def clean_paragraphs(text):
    """
    Split into paragraphs, merge stray fragments, normalize whitespace,
    style em-dash, convert ALL-CAPS → Title Case.
    """
    out = []
    for p in re.split(r'\n{2,}', text or ""):
        t = p.strip()
        if not t: continue

        # merge stray letters into words
        def mrg(m):
            cand = m.group(1)+m.group(2)
            return cand if is_english_word(cand) else m.group(0)
        t = re.sub(r'\b([A-Z])\s+([A-Za-z]{2,})', mrg, t)

        t = re.sub(r'\s+', ' ', t)  # normalize spaces

        if t.startswith('—'):       # em-dash styling
            core = t.lstrip('—').strip()
            core = re.sub(r'\s+,', ',', core).title()
            t = '— ' + core

        # ALL CAPS → Title Case
        if t.upper()==t and re.search(r'[A-Z]', t):
            t = t.title()

        out.append(t)
    return out

def to_html_section(emoji, title, paras):
    """Daily sections: <h3> header, first <p><strong>, rest <p>."""
    html = [f'<h3 style="margin-bottom:0.3em">{emoji} {title}</h3>']
    for i,p in enumerate(paras):
        if i==0:
            html.append(f'<p><strong>{p}</strong></p>')
        else:
            html.append(f'<p>{p}</p>')
    return "\n".join(html)

def to_html_weekly(emoji, title, raw):
    """
    Weekly section: split on lines, first line=WEEK I (bold),
    second line= subtitle, ornament, then body paras.
    """
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    week_num   = lines[0] if len(lines)>0 else ""
    week_title = lines[1] if len(lines)>1 else ""
    # the rest lines form a single block, re-join then re-split into paragraphs
    body_text = "\n\n".join(lines[2:]) if len(lines)>2 else ""
    paras     = clean_paragraphs(body_text)

    html = []
    html.append(f'<h3 style="margin-bottom:0.3em">{emoji} {title}</h3>')
    if week_num:
        html.append(f'<p><strong>{week_num}</strong></p>')
    if week_title:
        html.append(f'<p><em>{week_title}</em></p>')
    # centered ornament
    html.append('<p style="text-align:center; margin:0.5em 0;">❧</p>')
    for p in paras:
        html.append(f'<p>{p}</p>')
    return "\n".join(html)

def send_email(override_date=None):
    # 1) figure out the date in AEST
    if override_date:
        try:
            ref = datetime.strptime(override_date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid --date, use YYYY-MM-DD"); return
    else:
        now_utc = datetime.now(timezone.utc)
        ref = (now_utc + timedelta(hours=10)).date()

    md = (ref.month, ref.day)

    # 2) load CSV and find matching row (month+day)
    row = None
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            parts = r.get("Date","").split("/")
            if len(parts)!=3: continue
            try:
                d,m,y = map(int, parts)
            except:
                continue
            if (m,d)==md:
                row = r
                break

    if not row or not row.get("Daily Stoic","").strip():
        print(f"No daily entry for {ref.strftime('%d/%m')}")
        return

    # 3) extract fields
    stoic   = row["Daily Stoic"]
    dad     = row["Daily Dad"]
    thought = row["Todays Thought"]
    week    = row.get("Week","").strip()

    # 4) build subject and top header
    subject     = ref.strftime("Daily Reflection – %A, %B %d, %Y")
    header_html = f'<h2>These are your readings and meditations for {ref.strftime("%A, %B %d, %Y")}</h2>'

    # 5) assemble HTML
    parts = []
    if week:
        parts.append(to_html_weekly("📅", "Weekly Reflection", week))
        parts.append("<hr/>")

    parts.append(to_html_section("🧘‍♂️","Daily Stoic",       clean_paragraphs(stoic)))
    parts.append("<hr/>")
    parts.append(to_html_section("👨‍👧","Daily Dad",         clean_paragraphs(dad)))
    parts.append("<hr/>")
    parts.append(to_html_section("✍️",   "Today’s Thought", clean_paragraphs(thought)))

    if parts and parts[-1]=="<hr/>":
        parts.pop()

    html_body = (
        "<html><body style='font-family:sans-serif;line-height:1.4'>"
        + header_html + "\n"
        + "\n".join(parts) +
        "</body></html>"
    )

    # 6) send it
    msg = MIMEText(html_body, "html")
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

if __name__=="__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD override", default=None)
    args = p.parse_args()
    send_email(args.date)
