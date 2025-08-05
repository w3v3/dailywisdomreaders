import csv
import os
import re
import smtplib
import argparse
from email.mime.text import MIMEText
from datetime import datetime
from wordfreq import zipf_frequency

# === CONFIGURATION ===
CSV_PATH = "daily_readings_2025_clean.csv"  # Ensure this CSV is in the same folder
EMAIL_FROM = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_TO = "steve@thegoodnumbers.com.au"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USERNAME = "daily.stoic.wisdom.readings@gmail.com"
EMAIL_PASSWORD = "ohov qtwt gnar sxwb"  # Use an App Password if using Gmail with 2FA
# ======================


def is_english_word(word: str, min_freq: float = 3.0) -> bool:
    """Return True if `word` occurs frequently enough in English."""
    return zipf_frequency(word.lower(), 'en') >= min_freq


def clean_paragraphs(raw: str) -> str:
    """Fix stray fragments, normalize whitespace, and preserve paragraphs."""
    # 1) Split on 2+ newlines into rough paragraphs
    paras = re.split(r'\n{2,}', raw)
    out = []

    for p in paras:
        text = p.strip()
        if not text:
            continue

        # 2) Context‐aware merge: only glue single uppercase letter onto next
        #    word if that produces a real English word.
        def maybe_merge(m):
            letter, rest = m.group(1), m.group(2)
            candidate = letter + rest
            return candidate if is_english_word(candidate) else m.group(0)

        text = re.sub(r'\b([A-Z])\s+([A-Za-z]{2,})', maybe_merge, text)

        # 3) Collapse all remaining whitespace/newlines into single spaces
        text = re.sub(r'\s+', ' ', text)

        # 4) Normalize attribution lines (beginning with an em-dash)
        if text.startswith('—'):
            core = text.lstrip('—').strip()
            core = re.sub(r'\s+,', ',', core).title()
            text = '— ' + core

        out.append(text)

    # 5) Re-join true paragraphs with double line breaks
    return "\n\n".join(out)


def to_html_section(emoji: str, title: str, entry: str) -> str:
    """Wrap cleaned entry in HTML, bolding the first paragraph (date/title)."""
    paras = entry.split("\n\n")
    html = [f'<p><strong>{paras[0]}</strong></p>']
    for paragraph in paras[1:]:
        html.append(f'<p>{paragraph}</p>')
    header = f'<h3>{emoji} {title}</h3>'
    return header + "\n" + "\n".join(html)


def send_email(for_date: str):
    # Load and find today’s (or overridden) row
    stoic_raw = dad_raw = None
    with open(CSV_PATH, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Date'] == for_date:
                stoic_raw = row['Daily Stoic']
                dad_raw = row['Daily Dad']
                break

    if stoic_raw is None:
        print(f"No entry found for {for_date}")
        return

    # Clean and convert to HTML
    stoic_html = to_html_section("🧘‍♂️", "Daily Stoic",
                                 clean_paragraphs(stoic_raw))
    dad_html = to_html_section("👨‍👧", "Daily Dad", clean_paragraphs(dad_raw))
    html_body = f"""\
<html>
  <body style="font-family: sans-serif; line-height:1.4;">
    {stoic_html}
    <hr/>
    {dad_html}
  </body>
</html>
"""

    # Prepare MIME email
    msg = MIMEText(html_body, 'html')
    subject = datetime.strptime(for_date, "%Y-%m-%d")\
                      .strftime("Daily Stoic + Dad - %A, %B %d, %Y")
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    # Send
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Email sent for {for_date}")
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send Daily Stoic + Dad email")
    parser.add_argument(
        "--date",
        help="Override date in YYYY-MM-DD format (defaults to today)",
        default=None)
    args = parser.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
            run_date = args.date
        except ValueError:
            print("Invalid --date format. Use YYYY-MM-DD")
            exit(1)
    else:
        run_date = datetime.now().strftime("%Y-%m-%d")

    send_email(run_date)
