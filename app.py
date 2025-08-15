#!/usr/bin/env python3
import csv
import re
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for
from wordfreq import zipf_frequency

# ========= CONFIGURATION =========
CSV_PATH = os.getenv('CSV_PATH', 'sample_data.csv')
TIMEZONE_OFFSET = 10  # AEST (UTC+10)

# Text processing constants
COMMON_WORD_THRESHOLD = 2.5
MERGE_WORD_THRESHOLD = 3.0
SPLIT_WORD_THRESHOLD = 3.0
ACRONYMS = {"UCLA", "NASA", "AI", "SQL", "USA", "UK", "EU", "API", "HTTP", "HTTPS", "XML", "JSON"}
CANONICAL_NAMES = [
    "Marcus Aurelius", "Aurelius", "Marcus", "Seneca", "Epictetus", "Zeno", 
    "Cleanthes", "Chrysippus", "Musonius Rufus", "Musonius", "Rufus",
    "Antoninus Pius", "Antoninus", "Pius", "Hierocles", "Cato", "Diogenes",
]

# ========= TEXT PROCESSOR =========
class TextProcessor:
    def __init__(self):
        self.name_patterns = self._build_name_patterns()
        # Fixed regex patterns with proper escaping
        self.quote_attr_regex = re.compile(
            r'^\s*([""\u201c\u201d][^""\u201c\u201d]+[""\u201c\u201d])\s*(?:([\u2014\u2013-]\s*[A-Z][A-Za-z0-9 .,\u2019\u2018\'\u201c\u201d\u2014\u2013\-,:;()]+))?\s*$'
        )
        self.quote_separation_regex = re.compile(
            r'([""\u201c\u201d][^""\u201c\u201d]+[""\u201c\u201d])\s*((?:[\u2014\u2013-])\s*[A-Z][A-Za-z0-9 .,\u2019\u2018\'\u201c\u201d\u2014\u2013\-,:;()]+)'
        )
    
    def _build_name_patterns(self):
        patterns = []
        for name in CANONICAL_NAMES:
            tokens = name.split()
            token_patterns = []
            for tok in tokens:
                chars = list(tok)
                token_patterns.append(r"\s*".join(map(re.escape, chars)))
            full = r"\b" + r"\s+".join(token_patterns) + r"\b"
            patterns.append((re.compile(full, flags=re.IGNORECASE), name))
        return patterns
    
    @staticmethod
    def looks_like_acronym(s: str) -> bool:
        return s.isupper() and s in ACRONYMS
    
    def smart_title_token(self, token: str) -> str:
        if self.looks_like_acronym(token):
            return token
        if zipf_frequency(token.lower(), 'en') >= COMMON_WORD_THRESHOLD or len(token) >= 5:
            return token[:1].upper() + token[1:].lower()
        return token
    
    def smart_title_case(self, line: str) -> str:
        return re.sub(r"[A-Za-z]+", lambda m: self.smart_title_token(m.group(0)), line)
    
    def fix_proper_names(self, text: str) -> str:
        for pattern, canonical in self.name_patterns:
            text = pattern.sub(canonical, text)
        return text
    
    def clean_text_block(self, text: str) -> str:
        if not text:
            return ""
        
        t = text.strip()
        
        # Apply text cleaning logic
        def merge_if_word(match):
            candidate = (match.group(1) + match.group(2)).lower()
            return (match.group(1) + match.group(2) 
                   if zipf_frequency(candidate, 'en') >= MERGE_WORD_THRESHOLD 
                   else match.group(0))
        t = re.sub(r'\b([A-Z])\s+([A-Za-z]{2,})', merge_if_word, t)
        
        t = re.sub(r'\s+', ' ', t)
        
        def split_after_A(match):
            word = match.group(1)
            combo = ('a' + re.sub(r"[\u2019\u2018']", "", word)).lower()
            return 'A ' + word if zipf_frequency(combo, 'en') < SPLIT_WORD_THRESHOLD else 'A' + word
        t = re.sub(r'\bA([a-z][a-z]+(?:[\u2019\u2018\']s)?)\b', split_after_A, t)
        
        t = re.sub(r'\bA\s+t\b', 'At', t)
        t = re.sub(r'\bA\s+n\b', 'An', t)
        
        def split_after_I(match):
            word = match.group(1)
            return 'I ' + word if zipf_frequency(word.lower(), 'en') >= SPLIT_WORD_THRESHOLD else 'I' + word
        t = re.sub(r'\bI([a-z]{2,})\b', split_after_I, t)
        
        if t.startswith('\u2014'):  # em-dash
            core = t.lstrip('\u2014').strip()
            core = re.sub(r'\s+,', ',', core)
            t = '\u2014 ' + self.smart_title_case(core)
        
        if t and t.upper() == t and any(c.isalpha() for c in t):
            t = self.smart_title_case(t)
        
        t = self.fix_proper_names(t)
        return t
    
    def format_for_web(self, text: str) -> str:
        """Format text for web display (convert to HTML-safe format)"""
        cleaned = self.clean_text_block(text)
        # Convert line breaks to HTML
        return cleaned.replace('\n', '<br>')
    
    def process_section_content(self, raw_content: str) -> Dict[str, str]:
        """Process section content into structured format"""
        if not raw_content:
            return {"title": "", "subtitle": "", "content": ""}
        
        lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
        
        result = {
            "title": self.clean_text_block(lines[0]) if len(lines) > 0 else "",
            "subtitle": self.clean_text_block(lines[1]) if len(lines) > 1 else "",
            "content": ""
        }
        
        if len(lines) > 2:
            content_lines = lines[2:]
            content = "\n\n".join(content_lines)
            result["content"] = self.format_for_web(content)
        
        return result
    
    def process_weekly_content(self, raw_content: str) -> Dict[str, str]:
        """Process weekly content with special handling"""
        if not raw_content:
            return {"title": "", "subtitle": "", "content": ""}
        
        original_lines = raw_content.splitlines()
        content_indices = [i for i, line in enumerate(original_lines) if line.strip()]
        
        if not content_indices:
            return {"title": "", "subtitle": "", "content": ""}
        
        first_idx = content_indices[0]
        header1 = original_lines[first_idx].strip()
        header2 = original_lines[content_indices[1]].strip() if len(content_indices) > 1 else ""
        
        start_body = (content_indices[1] + 1) if len(content_indices) > 1 else (first_idx + 1)
        body = "\n".join(original_lines[start_body:])
        
        if body:
            body = re.sub(r'(?<!\n)\n(?!\n)', ' ', body)
            body = re.sub(r'\n{3,}', '\n\n', body)
            body = re.sub(r'\bI\s+t\b', 'It', body)
            body = re.sub(r"(?:\bI\s+t)([\u2019\u2018\']s)\b", r"It\1", body)
            body = self.quote_separation_regex.sub(lambda m: f'\n\n{m.group(1)} {m.group(2)}\n\n', body)
            body = re.sub(r'\n{3,}', '\n\n', body).strip()
        
        return {
            "title": self.clean_text_block(header1),
            "subtitle": self.clean_text_block(header2),
            "content": self.format_for_web(body) if body else ""
        }

# ========= DATA ACCESS =========
class ReadingsDataAccess:
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self.processor = TextProcessor()
    
    def get_date_list(self) -> list:
        """Get list of all available dates"""
        dates = []
        try:
            with open(self.csv_path, encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    date_str = row.get("Date", "").strip()
                    if date_str and self._is_valid_date_format(date_str):
                        dates.append(date_str)
        except Exception as e:
            print(f"Error reading CSV: {e}")
        return dates
    
    def _is_valid_date_format(self, date_str: str) -> bool:
        try:
            parts = date_str.split("/")
            if len(parts) == 3:
                int(parts[0]), int(parts[1]), int(parts[2])
                return True
        except ValueError:
            pass
        return False
    
    def find_reading_by_date(self, target_date: datetime.date) -> Optional[Dict[str, Any]]:
        target_month_day = (target_date.month, target_date.day)
        
        try:
            with open(self.csv_path, encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    date_str = row.get("Date", "").strip()
                    if not date_str:
                        continue
                    
                    try:
                        parts = date_str.split("/")
                        if len(parts) != 3:
                            continue
                        day, month, year = map(int, parts)
                        if (month, day) == target_month_day:
                            return self._process_reading_data(row)
                    except ValueError:
                        continue
        except Exception as e:
            print(f"Error accessing data: {e}")
            return None
        
        return None
    
    def _process_reading_data(self, raw_row: Dict[str, str]) -> Dict[str, Any]:
        """Process raw CSV row into structured reading data"""
        return {
            "date": raw_row.get("Date", ""),
            "daily_stoic": self.processor.process_section_content(raw_row.get("Daily Stoic", "")),
            "daily_dad": self.processor.process_section_content(raw_row.get("Daily Dad", "")),
            "todays_thought": self.processor.process_section_content(raw_row.get("Todays Thought", "")),
            "weekly": self.processor.process_weekly_content(raw_row.get("Week", "")),
            "has_weekly": bool(raw_row.get("Week", "").strip())
        }
    
    def get_current_aest_date(self) -> datetime.date:
        """Get current AEST date"""
        now_utc = datetime.now(timezone.utc)
        return (now_utc + timedelta(hours=TIMEZONE_OFFSET)).date()

# ========= FLASK APP =========
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize data access
try:
    data_access = ReadingsDataAccess(CSV_PATH)
except Exception as e:
    print(f"Warning: Could not initialize data access: {e}")
    data_access = None

@app.route('/')
def index():
    """Home page - today's reading"""
    if not data_access:
        return render_template('error.html', message="Data source not available")
    
    today = data_access.get_current_aest_date()
    reading = data_access.find_reading_by_date(today)
    
    if not reading:
        return render_template('no_reading.html', date=today.strftime('%A, %B %d, %Y'))
    
    return render_template('reading.html', reading=reading, date=today.strftime('%A, %B %d, %Y'))

@app.route('/date/<date_str>')
def reading_by_date(date_str):
    """View reading for specific date (YYYY-MM-DD format)"""
    if not data_access:
        return render_template('error.html', message="Data source not available")
    
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return render_template('error.html', message="Invalid date format")
    
    reading = data_access.find_reading_by_date(target_date)
    
    if not reading:
        return render_template('no_reading.html', date=target_date.strftime('%A, %B %d, %Y'))
    
    return render_template('reading.html', reading=reading, date=target_date.strftime('%A, %B %d, %Y'))

@app.route('/calendar')
def calendar_view():
    """Calendar view of all available readings"""
    if not data_access:
        return render_template('error.html', message="Data source not available")
    
    dates = data_access.get_date_list()
    return render_template('calendar.html', dates=dates)

@app.route('/api/reading')
def api_reading():
    """API endpoint for getting reading data"""
    if not data_access:
        return jsonify({"error": "Data source not available"}), 500
    
    date_param = request.args.get('date')
    
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
    else:
        target_date = data_access.get_current_aest_date()
    
    reading = data_access.find_reading_by_date(target_date)
    
    if not reading:
        return jsonify({"error": "No reading found for date"}), 404
    
    return jsonify(reading)

# Create a custom Jinja2 filter for date formatting
@app.template_filter('date_url')
def date_url_filter(date_str):
    """Convert DD/MM/YYYY to YYYY-MM-DD for URLs"""
    try:
        parts = date_str.split('/')
        if len(parts) == 3:
            day, month, year = parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except:
        pass
    return date_str

# Simple service worker for PWA
@app.route('/sw.js')
def service_worker():
    return '''
self.addEventListener('install', function(event) {
    console.log('Service Worker: Installed');
});

self.addEventListener('fetch', function(event) {
    // Basic caching strategy could go here
});
''', 200, {'Content-Type': 'application/javascript'}

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Daily Stoic Readings",
        "short_name": "Stoic",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#667eea",
        "theme_color": "#667eea",
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🧘‍♂️%3C/text%3E%3C/svg%3E",
                "sizes": "192x192",
                "type": "image/svg+xml"
            }
        ]
    })

if __name__ == '__main__':
    print("🧘‍♂️ Starting Daily Stoic Web App")
    print(f"📁 Using CSV file: {CSV_PATH}")
    print("🌐 Open http://localhost:5000 in your browser")
    print("📱 For mobile testing, use your local IP address")
    
    app.run(debug=True, host='0.0.0.0', port=5000)