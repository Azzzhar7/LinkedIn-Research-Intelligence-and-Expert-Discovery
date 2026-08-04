"""User-directed profile review browser.

This deliberately opens the next profile for the researcher to inspect and enter data
into the app. It does not scrape, scroll, or collect LinkedIn data automatically.
"""
from playwright.sync_api import sync_playwright


def open_for_review(url, browser_channel='chrome'):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=browser_channel, headless=False)
        page = browser.new_page()
        page.goto(url, wait_until='domcontentloaded')
        page.bring_to_front()
        # Browser stays available until the user closes it.
        page.wait_for_timeout(1_000)
        return 'Opened profile in a separate browser window. Review it, then return to this app to save the fields.'

