# Daily Stoic Readings Web App

A beautiful web application for displaying daily stoic readings, daily dad advice, and personal reflections. Built with Flask and featuring a modern, responsive design with PWA capabilities.

## Features

- 📅 **Daily Readings**: View today's stoic wisdom, parenting advice, and personal reflections
- 🗓️ **Calendar View**: Browse all available readings by date
- 📱 **Mobile Responsive**: Beautiful design that works on all devices
- 🎨 **Modern UI**: Glassmorphism design with smooth animations
- 🔄 **Progressive Web App**: Install on your device for offline access
- 🎯 **Intelligent Text Processing**: Advanced text cleaning and formatting

## Installation

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Open your browser** and go to `http://localhost:5000`

## Configuration

### CSV Data File

The app reads from a CSV file with the following columns:
- `Date`: Date in DD/MM/YYYY format
- `Daily Stoic`: Stoic philosophy content
- `Daily Dad`: Parenting advice content  
- `Todays Thought`: Personal reflection content
- `Week`: Weekly theme content (optional)

### Environment Variables

- `CSV_PATH`: Path to your CSV file (default: `sample_data.csv`)
- `SECRET_KEY`: Flask secret key for sessions
- `TIMEZONE_OFFSET`: Hours offset from UTC (default: 10 for AEST)

Example:
```bash
export CSV_PATH="/path/to/your/readings.csv"
export SECRET_KEY="your-secret-key"
python app.py
```

## Usage

### Viewing Today's Reading
- Navigate to the home page (`/`) to see today's reading
- Content is automatically formatted and cleaned for optimal reading

### Browsing by Date
- Visit `/calendar` to see all available readings
- Click any date to view that day's reading
- URLs use the format `/date/YYYY-MM-DD`

### API Access
- GET `/api/reading` - Today's reading in JSON format
- GET `/api/reading?date=YYYY-MM-DD` - Specific date's reading

## Text Processing Features

The app includes sophisticated text processing:

- **Smart Title Casing**: Automatically formats text with proper capitalization
- **Name Recognition**: Recognizes and properly formats historical names
- **Word Frequency Analysis**: Uses linguistic data to improve text formatting
- **Quote Extraction**: Identifies and formats quotations properly
- **HTML Formatting**: Converts text to web-friendly format with line breaks

## File Structure

```
daily-stoic-app/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── sample_data.csv       # Sample reading data
├── templates/            # HTML templates
│   ├── base.html        # Base template with styling
│   ├── reading.html     # Reading display template
│   ├── calendar.html    # Calendar view template
│   ├── error.html       # Error page template
│   └── no_reading.html  # No reading found template
└── README.md            # This file
```

## Development

The application uses:
- **Flask** for the web framework
- **Jinja2** for templating
- **wordfreq** for linguistic analysis
- **Modern CSS** with glassmorphism effects
- **Vanilla JavaScript** for interactive features

## Mobile Installation

On mobile devices, you can install this as a PWA:
1. Open in your mobile browser
2. Look for "Add to Home Screen" option
3. The app will behave like a native mobile app

## Customization

### Styling
Edit the CSS in `templates/base.html` to customize the appearance.

### Text Processing
Modify the `TextProcessor` class in `app.py` to adjust text cleaning behavior.

### Layout
Update the templates in the `templates/` directory to change the layout.

## License

This project is open source and available under the MIT License.