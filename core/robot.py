# Goal: Write a Python program that controls a web browser using Playwright to complete a fixed, single task (e.g., Log in, search for a specific product, and report its price).

# Actions: Your code must perform all necessary browser actions (Go to URL, Click, Type).

# Reliability: The code must include proper error handling so it doesn't crash on slow pages or missing elements.

# Output: The program should print a clear, final result to the console (e.g., "Success! Product ABC found").

import os
from playwright.sync_api import Playwright, sync_playwright, TimeoutError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import logging if available (for mcpAI integration)
try:
    import sys
    from pathlib import Path
    # Add parent directory to path to import logging_config
    parent_dir = Path(__file__).resolve().parent.parent
    if (parent_dir / "mcpAI" / "logging_config.py").exists():
        sys.path.insert(0, str(parent_dir))
        from mcpAI.logging_config import setup_logging, get_logger
        setup_logging()
        logger = get_logger(__name__)
    else:
        logger = None
except Exception:
    logger = None


def run(playwright: Playwright) -> None:
    """Run the robot automation task."""
    # Get credentials from environment variables
    username = os.getenv("SAUCEDEMO_USERNAME", "standard_user")
    password = os.getenv("SAUCEDEMO_PASSWORD", "secret_sauce")
    
    # Get browser configuration from environment
    headless = os.getenv("HEADLESS_MODE", "false").lower() == "true"
    slow_mo = int(os.getenv("BROWSER_SLOW_MO", "1000"))
    
    if logger:
        logger.info(f"Starting robot (headless={headless}, slow_mo={slow_mo})")
    
    # Launch browser
    browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Step 1: Go to login page
        if logger:
            logger.info("Opening the login page")
        print("Opening the login page...")
        #30 second timeout
        page.goto("https://www.saucedemo.com/", timeout=30000)

        # Step 2: Log in
        # Wait for input fields to ensure the page has loaded
        page.wait_for_selector("[data-test='username']", timeout=10000)
        if logger:
            logger.info("Logging in")
        print("Logging in...")
        page.locator("[data-test=\"username\"]").click()
        page.locator("[data-test=\"username\"]").fill(username)
        page.locator("[data-test=\"password\"]").click()
        page.locator("[data-test=\"password\"]").fill(password)
        page.locator("[data-test=\"login-button\"]").click()

        # Step 3: Click on a specific product (Sauce Labs Backpack)
        # Wait for product detail elements before reading
        page.wait_for_selector("[data-test='inventory-item-name']", timeout=10000)
        page.wait_for_selector("[data-test='inventory-item-price']", timeout=10000)
        if logger:
            logger.info("Clicking on product")
        page.locator("[data-test=\"item-4-title-link\"]").click()
        page.locator("[data-test=\"inventory-item-price\"]").click()

        # Step 4: Extract product name and price
        product_name = page.locator("[data-test='inventory-item-name']").inner_text()
        price = page.locator("[data-test='inventory-item-price']").inner_text()

        # Step 5: Print result to console
        result_msg = f"Success! '{product_name}' found at price {price}."
        if logger:
            logger.info(f"Task completed: {result_msg}")
        print(result_msg)
    except TimeoutError:
        error_msg = "Timeout: Page or element took too long to load."
        if logger:
            logger.error(error_msg)
        print(f" {error_msg}")
    except Exception as e:
        error_msg = f"Error: {e}"
        if logger:
            logger.error(error_msg, exc_info=True)
        print(f" {error_msg}")
    finally:
        if logger:
            logger.info("Closing browser")
        print("Closing browser...")
        # Step 6: Close browser
        context.close()
        browser.close()

# Run the script
if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
