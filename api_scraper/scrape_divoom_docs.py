#!/usr/bin/env python3
"""
Divoom API Documentation Scraper
Fetches content from JavaScript-rendered documentation pages
"""

import asyncio
import json
from playwright.async_api import async_playwright
from pathlib import Path

# All the URLs organized by category
URLS = {
    "base": [
        "https://docin.divoom-gz.com/web/#/5/146"
    ],
    "system_settings": [
        "https://docin.divoom-gz.com/web/#/5/147",
        "https://docin.divoom-gz.com/web/#/5/178",
        "https://docin.divoom-gz.com/web/#/5/179",
        "https://docin.divoom-gz.com/web/#/5/180",
        "https://docin.divoom-gz.com/web/#/5/181",
        "https://docin.divoom-gz.com/web/#/5/182",
        "https://docin.divoom-gz.com/web/#/5/183",
        "https://docin.divoom-gz.com/web/#/5/184",
        "https://docin.divoom-gz.com/web/#/5/185",
        "https://docin.divoom-gz.com/web/#/5/186",
        "https://docin.divoom-gz.com/web/#/5/187",
        "https://docin.divoom-gz.com/web/#/5/188",
        "https://docin.divoom-gz.com/web/#/5/189",
        "https://docin.divoom-gz.com/web/#/5/190",
        "https://docin.divoom-gz.com/web/#/5/191",
        "https://docin.divoom-gz.com/web/#/5/192",
        "https://docin.divoom-gz.com/web/#/5/193",
        "https://docin.divoom-gz.com/web/#/5/194",
        "https://docin.divoom-gz.com/web/#/5/195",
        "https://docin.divoom-gz.com/web/#/5/196",
        "https://docin.divoom-gz.com/web/#/5/197",
        "https://docin.divoom-gz.com/web/#/5/198",
        "https://docin.divoom-gz.com/web/#/5/314",
        "https://docin.divoom-gz.com/web/#/5/315"
    ],
    "music_play": [
        "https://docin.divoom-gz.com/web/#/5/199",
        "https://docin.divoom-gz.com/web/#/5/200",
        "https://docin.divoom-gz.com/web/#/5/201",
        "https://docin.divoom-gz.com/web/#/5/202",
        "https://docin.divoom-gz.com/web/#/5/203",
        "https://docin.divoom-gz.com/web/#/5/204",
        "https://docin.divoom-gz.com/web/#/5/205",
        "https://docin.divoom-gz.com/web/#/5/206",
        "https://docin.divoom-gz.com/web/#/5/207",
        "https://docin.divoom-gz.com/web/#/5/208",
        "https://docin.divoom-gz.com/web/#/5/209",
        "https://docin.divoom-gz.com/web/#/5/210",
        "https://docin.divoom-gz.com/web/#/5/211",
        "https://docin.divoom-gz.com/web/#/5/212",
        "https://docin.divoom-gz.com/web/#/5/213",
        "https://docin.divoom-gz.com/web/#/5/214",
        "https://docin.divoom-gz.com/web/#/5/215"
    ],
    "alarm_memorial": [
        "https://docin.divoom-gz.com/web/#/5/246",
        "https://docin.divoom-gz.com/web/#/5/247",
        "https://docin.divoom-gz.com/web/#/5/248",
        "https://docin.divoom-gz.com/web/#/5/249",
        "https://docin.divoom-gz.com/web/#/5/250",
        "https://docin.divoom-gz.com/web/#/5/251",
        "https://docin.divoom-gz.com/web/#/5/252",
        "https://docin.divoom-gz.com/web/#/5/253",
        "https://docin.divoom-gz.com/web/#/5/254"
    ],
    "timeplan": [
        "https://docin.divoom-gz.com/web/#/5/256",
        "https://docin.divoom-gz.com/web/#/5/257"
    ],
    "tool": [
        "https://docin.divoom-gz.com/web/#/5/264",
        "https://docin.divoom-gz.com/web/#/5/265"
    ],
    "sleep": [
        "https://docin.divoom-gz.com/web/#/5/266",
        "https://docin.divoom-gz.com/web/#/5/272",
        "https://docin.divoom-gz.com/web/#/5/273",
        "https://docin.divoom-gz.com/web/#/5/274",
        "https://docin.divoom-gz.com/web/#/5/275",
        "https://docin.divoom-gz.com/web/#/5/276",
        "https://docin.divoom-gz.com/web/#/5/277"
    ],
    "game": [
        "https://docin.divoom-gz.com/web/#/5/278",
        "https://docin.divoom-gz.com/web/#/5/279",
        "https://docin.divoom-gz.com/web/#/5/280",
        "https://docin.divoom-gz.com/web/#/5/281"
    ],
    "light": [
        "https://docin.divoom-gz.com/web/#/5/287",
        "https://docin.divoom-gz.com/web/#/5/288",
        "https://docin.divoom-gz.com/web/#/5/289",
        "https://docin.divoom-gz.com/web/#/5/290",
        "https://docin.divoom-gz.com/web/#/5/291",
        "https://docin.divoom-gz.com/web/#/5/292",
        "https://docin.divoom-gz.com/web/#/5/293",
        "https://docin.divoom-gz.com/web/#/5/294",
        "https://docin.divoom-gz.com/web/#/5/295",
        "https://docin.divoom-gz.com/web/#/5/296",
        "https://docin.divoom-gz.com/web/#/5/297",
        "https://docin.divoom-gz.com/web/#/5/298",
        "https://docin.divoom-gz.com/web/#/5/299",
        "https://docin.divoom-gz.com/web/#/5/300",
        "https://docin.divoom-gz.com/web/#/5/301",
        "https://docin.divoom-gz.com/web/#/5/302",
        "https://docin.divoom-gz.com/web/#/5/303",
        "https://docin.divoom-gz.com/web/#/5/304",
        "https://docin.divoom-gz.com/web/#/5/305",
        "https://docin.divoom-gz.com/web/#/5/306",
        "https://docin.divoom-gz.com/web/#/5/307",
        "https://docin.divoom-gz.com/web/#/5/308",
        "https://docin.divoom-gz.com/web/#/5/309",
        "https://docin.divoom-gz.com/web/#/5/310",
        "https://docin.divoom-gz.com/web/#/5/311",
        "https://docin.divoom-gz.com/web/#/5/312",
        "https://docin.divoom-gz.com/web/#/5/313"
    ]
}


async def fetch_single_page(url, debug=False, screenshot_path=None):
    """
    Open a fresh browser, load ONE page, extract content, close browser
    Completely isolated - no state carried between pages
    """
    async with async_playwright() as p:
        # Fresh browser instance
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        try:
            print(f"  → Opening fresh browser instance...")
            print(f"  → Loading {url}")

            # Load the page
            await page.goto(url, wait_until="load", timeout=30000)

            # Wait for content to render
            print(f"  → Waiting for content to render...")
            await asyncio.sleep(3)

            # Wait for the editor content element
            try:
                await page.wait_for_selector('#editor-md', timeout=5000)
                print(f"  ✓ Content area found")
            except:
                print(f"  ⚠ Content area not found, continuing...")

            # Extract the title
            title = await page.title()

            # Extract the main content
            print(f"  → Extracting content...")
            content_data = await page.evaluate('''() => {
                // Target the specific content areas
                const contentSelectors = [
                    '#editor-md',
                    '#doc-body',
                    '.page_content_main',
                    '#page_md_content',
                    '.editormd-html-preview',
                    '.markdown-body'
                ];

                let content = '';
                let heading = '';

                // Try each selector
                for (const selector of contentSelectors) {
                    const element = document.querySelector(selector);
                    if (element && element.innerText.trim().length > 50) {
                        content = element.innerText.trim();

                        // Try to get heading
                        const h1 = element.querySelector('h1, h2, h3');
                        if (h1) {
                            heading = h1.innerText.trim();
                        }

                        break;
                    }
                }

                // If still no heading, try the doc-title-box
                if (!heading) {
                    const titleBox = document.querySelector('#doc-title-box, .doc-title-box, .page-header h1');
                    if (titleBox) {
                        heading = titleBox.innerText.trim();
                    }
                }

                return { content, heading };
            }''')

            content = content_data['content']
            heading = content_data['heading']

            # If still no substantial content, try fallback
            if not content or len(content.strip()) < 50:
                print(f"  ⚠ Main content empty, trying fallback...")
                content = await page.evaluate('''() => {
                    const main = document.querySelector('.container, .doc-container, main, .content');
                    if (main) {
                        const clone = main.cloneNode(true);
                        const toRemove = clone.querySelectorAll('.sidebar, .left-side, nav, .navigation, .menu');
                        toRemove.forEach(el => el.remove());
                        return clone.innerText.trim();
                    }
                    return document.body.innerText.trim();
                }''')

            print(f"  ✓ Extracted {len(content)} characters")

            # Take screenshot if requested
            if debug and screenshot_path:
                await page.screenshot(path=str(screenshot_path))
                print(f"  → Screenshot saved: {screenshot_path}")

            result = {
                'url': url,
                'title': title,
                'heading': heading,
                'content': content.strip() if content else '',
                'content_length': len(content) if content else 0
            }

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            result = {
                'url': url,
                'error': str(e)
            }

        finally:
            # ALWAYS close the browser
            print(f"  → Closing browser instance")
            await browser.close()

        return result


async def scrape_all_docs(debug=False):
    """
    Scrape all documentation pages
    Each URL gets a completely fresh browser instance
    """
    results = {}
    total_urls = sum(len(urls) for urls in URLS.values())
    current = 0

    # Create debug directory if needed
    if debug:
        debug_dir = Path("debug_screenshots")
        debug_dir.mkdir(exist_ok=True)

    # Iterate through each category
    for category, urls in URLS.items():
        print(f"\n{'='*60}")
        print(f"Processing category: {category}")
        print(f"{'='*60}")

        results[category] = []

        for url in urls:
            current += 1
            print(f"\n[{current}/{total_urls}] {url}")

            # Prepare screenshot path if debug mode
            screenshot_path = None
            if debug:
                screenshot_path = debug_dir / f"{category}_{current}.png"

            # Fetch this ONE page with a fresh browser
            page_data = await fetch_single_page(url, debug=debug, screenshot_path=screenshot_path)

            results[category].append(page_data)

            # Small delay between pages
            await asyncio.sleep(0.5)

    return results


async def main():
    """
    Main function to run the scraper
    """
    import sys

    # Check for debug flag
    debug = '--debug' in sys.argv or '-d' in sys.argv

    print("Starting Divoom API documentation scraper...")
    print(f"Total URLs to scrape: {sum(len(urls) for urls in URLS.values())}")
    if debug:
        print("🐛 Debug mode enabled - will save screenshots")

    # Scrape all documentation
    results = await scrape_all_docs(debug=debug)

    # Count successes and failures
    total_success = sum(1 for pages in results.values()
                        for p in pages if 'error' not in p)
    total_failed = sum(1 for pages in results.values()
                       for p in pages if 'error' in p)

    print(f"\n{'='*60}")
    print(f"Scraping complete!")
    print(f"✓ Success: {total_success}")
    print(f"✗ Failed: {total_failed}")
    print(f"{'='*60}\n")

    # Save results to JSON
    output_dir = Path("divoom_docs")
    output_dir.mkdir(exist_ok=True)

    # Save full results as JSON
    json_file = output_dir / "divoom_api_full.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved full results to: {json_file}")

    # Save individual category files as markdown
    for category, pages in results.items():
        md_file = output_dir / f"{category}.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(f"# {category.replace('_', ' ').title()}\n\n")

            for idx, page in enumerate(pages, 1):
                if 'error' in page:
                    f.write(f"## Page {idx}: Error\n")
                    f.write(f"URL: {page['url']}\n\n")
                    f.write(f"Error: {page['error']}\n\n")
                else:
                    if page.get('heading'):
                        f.write(f"## {page['heading']}\n\n")
                    else:
                        f.write(f"## Page {idx}\n\n")

                    f.write(f"**URL:** {page['url']}\n\n")
                    f.write(
                        f"**Content Length:** {page.get('content_length', 0)} characters\n\n")
                    f.write(f"{page['content']}\n\n")
                    f.write(f"---\n\n")

        success_count = sum(1 for p in pages if 'error' not in p)
        print(
            f"✓ Saved {category} ({success_count}/{len(pages)} successful) to: {md_file}")

    # Create a summary
    summary_file = output_dir / "README.md"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("# Divoom API Documentation\n\n")
        f.write("Scraped from: https://docin.divoom-gz.com/web/\n\n")
        f.write("## Summary\n\n")
        f.write(f"- **Total pages scraped:** {total_success + total_failed}\n")
        f.write(f"- **Successful:** {total_success}\n")
        f.write(f"- **Failed:** {total_failed}\n\n")
        f.write("## Categories\n\n")

        for category, pages in results.items():
            success = sum(1 for p in pages if 'error' not in p)
            total = len(pages)
            status = "✓" if success == total else "⚠" if success > 0 else "✗"
            f.write(
                f"{status} **{category.replace('_', ' ').title()}**: {success}/{total} pages successfully scraped\n")

        f.write("\n## Files\n\n")
        f.write("- `divoom_api_full.json` - Complete data in JSON format\n")
        for category in results.keys():
            f.write(
                f"- `{category}.md` - {category.replace('_', ' ').title()} documentation\n")

    print(f"\n✓ Saved summary to: {summary_file}")
    print(f"\n✅ All done! Check the 'divoom_docs' folder for results.")

    if total_failed > 0:
        print(
            f"\n⚠️  Note: {total_failed} pages failed to scrape. Check the markdown files for error details.")


if __name__ == "__main__":
    asyncio.run(main())
