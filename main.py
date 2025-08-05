import csv
import os
import re
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime
from wordfreq import zipf_frequency

# === CONFIGURATION ===
CSV_PATH       = "daily_readings_with_meditation.csv"  # Ensure this CSV is in the same folder
EMAIL_FROM     = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_TO       = "steve@thegoodnumbers.com.au"
SMTP_SERVER    = "smtp.gmail.com"
SMTP_PORT      = 587
EMAIL_USERNAME = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_PASSWORD = "ohov qtwt gnar sxwb"  # Use an App Password if using Gmail with 2FA
# ======================

def is_english_word(word: str, min_freq: float = 3.0) -> bool:
    """Return True if `word` occurs frequently enough in English."""
    return zipf_frequency(word.lower(), 'en') >= min_freq

def clean_paragraphs(raw: str) -> str:
    """Fix stray fragments, normalize whitespace, and preserve paragraphs."""
    paras = re.split(r'\n{2,}', raw)
    out = []
    for p in paras:
        text = p.strip()
        if not text:
            continue

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
    """Wrap cleaned entry in HTML, bolding the first paragraph."""
    paras = entry.split("\n\n")
    html = [f'<p><strong>{paras[0]}</strong></p>'] if paras else []
    for para in paras[1:]:
        html.append(f'<p>{para}</p>')
    return f'<h3>{emoji} {title}</h3>\n' + "\n".join(html)

def send_email(for_date: str):
    stoic_raw = dad_raw = med_raw = None

    # 1) Read the CSV for today’s entries, using cp1252 to handle em-dashes and smart quotes
    with open(CSV_PATH, newline='', encoding='cp1252') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Date'] == for_date:
                stoic_raw = row.get('Daily Stoic', '')
                dad_raw   = row.get('Daily Dad', '')
                med_raw   = row.get('Todays meditation', '')
                break

    if stoic_raw is None:
        print(f"No entry found for {for_date}")
        return

    # 2) Build the top heading
    formatted_date = datetime.strptime(for_date, "%Y-%m-%d") \
                             .strftime("%A, %B %d, %Y")
    header_html = f'<h2>These are your readings and meditations for {formatted_date}</h2>'

    # 3) Build HTML for each section
    stoic_html = to_html_section("🧘‍♂️", "Daily Stoic", clean_paragraphs(stoic_raw))
    dad_html   = to_html_section("👨‍👧", "Daily Dad",   clean_paragraphs(dad_raw))
    med_html   = to_html_section("✍️",   "Today’s Meditation", clean_paragraphs(med_raw))

    # 4) Assemble full HTML body
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

    # 5) Compose and send
    msg = MIMEText(html_body, 'html')
    subject = datetime.strptime(for_date, "%Y-%m-%d") \
                      .strftime("Daily Reflection – %A, %B %d, %Y")
    msg['Subject'] = subject
    msg['From']    = EMAIL_FROM
    msg['To']      = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Email sent for {for_date}")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Daily Reflection email")
    parser.add_argument("--date", help="YYYY-MM-DD to test (defaults to today)", default=None)
    args = parser.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            run_date = args.date
        except ValueError:
            print("Invalid --date format, use YYYY-MM-DD")
            exit(1)
    else:
        run_date = datetime.now().strftime("%Y-%m-%d")

    send_email(run_date)
