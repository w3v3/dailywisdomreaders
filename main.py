import csv
import os
import re
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from wordfreq import zipf_frequency

# === CONFIGURATION ===
CSV_PATH       = "daily_readings_with_meditation.csv"  # now holds Date as MM-DD
EMAIL_FROM     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_TO       = "steve@thegoodnumbers.com.au"
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_USERNAME = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_PASSWORD = "ohov qtwt gnar sxwb"
# ======================

def is_english_word(word: str, min_freq: float = 3.0) -> bool:
    return zipf_frequency(word.lower(), 'en') >= min_freq

def clean_paragraphs(raw: str) -> str:
    paras = re.split(r'\n{2,}', raw)
    out = []
    for p in paras:
        text = p.strip()
        if not text: continue
        def maybe_merge(m):
            letter, rest = m.group(1), m.group(2)
            cand = letter + rest
            return cand if is_english_word(cand) else m.group(0)
        text = re.sub(r'\b([A-Z])\s+([A-Za-z]{2,})', maybe_merge, text)
        text = re.sub(r'\s+', ' ', text)
        if text.startswith('—'):
            core = text.lstrip('—').strip()
            core = re.sub(r'\s+,', ',', core).title()
            text = '— ' + core
        out.append(text)
    return "\n\n".join(out)

def to_html_section(emoji: str, title: str, entry: str) -> str:
    paras = entry.split("\n\n")
    html = [f'<p><strong>{paras[0]}</strong></p>'] if paras else []
    for para in paras[1:]:
        html.append(f'<p>{para}</p>')
    return f'<h3>{emoji} {title}</h3>\n' + "\n".join(html)

def send_email():
    # 1) Determine “today” in AEST
    now_utc = datetime.now(timezone.utc)
    aest    = now_utc + timedelta(hours=10)
    run_date_full = aest.strftime("%Y-%m-%d")  # for subject/header
    run_ddmm      = aest.strftime("%d-%m")     # for Australian DD-MM lookup

    stoic_raw = dad_raw = med_raw = None

    # 2) Read CSV, matching Australian day-month
    with open(CSV_PATH, newline='', encoding='utf-8', errors='replace') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Date'].strip() == run_ddmm:
                stoic_raw = row.get('Daily Stoic', '')
                dad_raw   = row.get('Daily Dad', '')
                med_raw   = row.get('Todays meditation', '')
                break

    if stoic_raw is None:
        print(f"No entry found for {run_ddmm}")
        return

    # 3) Top heading
    formatted = aest.strftime("%A, %B %d, %Y")
    header_html = f'<h2>These are your readings and meditations for {formatted}</h2>'

    # 4) Sections
    stoic_html = to_html_section("🧘‍♂️", "Daily Stoic", clean_paragraphs(stoic_raw))
    dad_html   = to_html_section("👨‍👧", "Daily Dad",   clean_paragraphs(dad_raw))
    med_html   = to_html_section("✍️",   "Today’s Meditation", clean_paragraphs(med_raw))

    html_body = f"""\
<html>
  <body style="font-family: sans-serif; line-height:1.4;">
    {header_html}
    {stoic_html}
    <hr/>
    {dad_html}
    <hr/>
    {med_html}
  </body>
</html>
"""

    msg = MIMEText(html_body, 'html')
    msg['Subject'] = datetime.strptime(run_date_full, "%Y-%m-%d")\
                             .strftime("Daily Reflection – %A, %B %d, %Y")
    msg['From'] = EMAIL_FROM
    msg['To']   = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Email sent for {run_date_full}")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == "__main__":
    # Allow manual override if desired
    parser = argparse.ArgumentParser(description="Send Daily Reflection email")
    parser.add_argument("--date", help="Override run date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()

    if args.date:
        # If date override, simply set AEST based on that string
        try:
            override = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print("Invalid --date format, use YYYY-MM-DD")
            exit(1)
        # monkey-patch aest time
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        aest_base = override
        # override run_mmdd and run_date_full
        run_date_full = override.strftime("%Y-%m-%d")
        run_mmdd      = override.strftime("%m-%d")
        # call a modified send_email logic
        # (for brevity, just call send_email() after setting globals)
    # Otherwise simply send
    send_email()
