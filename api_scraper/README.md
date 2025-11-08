# Divoom API Documentation Scraper

This script fetches all the Divoom Bluetooth API documentation from the JavaScript-rendered documentation site.

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

## Installation

1. Install the required Python packages:

```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:

```bash
playwright install chromium
```

## Usage

Run the scraper:

```bash
python scrape_divoom_docs.py
```

Run with debug mode (saves screenshots):

```bash
python scrape_divoom_docs.py --debug
```

The script will:

1. Launch a headless Chrome browser
2. Navigate to each of the 93 documentation URLs
3. Wait for JavaScript content to load
4. Extract the documentation text
5. Save results in the `divoom_docs/` folder

## Output

The script creates a `divoom_docs/` folder containing:

- `divoom_api_full.json` - Complete data in JSON format
- `base.md` - Base/protocol introduction documentation
- `system_settings.md` - System settings commands
- `music_play.md` - Music playback controls
- `alarm_memorial.md` - Alarm and memorial features
- `timeplan.md` - Time planning features
- `tool.md` - Tool commands
- `sleep.md` - Sleep-related features
- `game.md` - Game controls
- `light.md` - Light/display controls
- `README.md` - Summary of scraped content

## Categories Covered

The scraper fetches documentation from these categories:

- **Base** (1 URL) - Protocol introduction and basics
- **System Settings** (24 URLs) - Device configuration commands
- **Music Play** (17 URLs) - Music playback controls
- **Alarm Memorial** (9 URLs) - Alarms and reminders
- **Timeplan** (2 URLs) - Scheduling features
- **Tool** (2 URLs) - Utility commands
- **Sleep** (7 URLs) - Sleep mode and timers
- **Game** (4 URLs) - Game controls
- **Light** (27 URLs) - Display and lighting controls

## How It Works

The script uses Playwright (a headless browser automation tool) to:

1. Launch a Chromium browser in headless mode
2. Navigate to each URL in the documentation
3. Wait for the page to fully load (using `domcontentloaded` event)
4. Extract text content using a flexible JavaScript-based approach that:
   - Tries multiple common content selectors
   - Falls back to extracting all body text if specific selectors don't match
   - Removes navigation and sidebar elements for cleaner output
5. Save the extracted content in both JSON and Markdown formats

**Robust Content Extraction:**
The script doesn't rely on specific CSS selectors that might change or be missing. Instead, it:

- Uses JavaScript evaluation to try multiple content extraction strategies
- Gracefully falls back if primary methods don't work
- Captures debug information (content length, errors) to help troubleshooting
- Can take screenshots with `--debug` flag to see exactly what the browser rendered

This approach is necessary because the documentation site uses hash-based routing (URLs like `#/5/146`), which requires JavaScript to render the content. Simple HTTP requests won't work.

## Troubleshooting

**Browser install fails:**

```bash
# Try installing with sudo (Linux/Mac)
sudo playwright install chromium

# Or specify the browser manually
python -m playwright install chromium
```

**Script fails or times out:**

- Check your internet connection
- The site might be slow or temporarily unavailable
- Run with `--debug` flag to save screenshots and see what the browser is actually loading
- Check the `debug_screenshots/` folder to see what content was rendered

**Missing or incomplete content:**

- Run with `--debug` flag to take screenshots
- Check the `divoom_api_full.json` for any error messages
- The script now uses flexible content extraction that doesn't depend on specific CSS selectors
- Content is extracted using JavaScript evaluation, which is more robust than selector-based extraction

## Customization

The content extraction is designed to be flexible and work without modification. However, if you need to adjust the behavior:

**Adjust wait time:**

```python
# In fetch_page_content(), change this line:
await asyncio.sleep(2)  # Increase if content takes longer to render
```

**Modify content extraction:**
The script uses JavaScript evaluation to extract content. You can modify the JavaScript code in the `page.evaluate()` call to add custom selectors or filtering logic.

## License

This is a utility script for personal use. Respect the terms of service of the documentation website.
