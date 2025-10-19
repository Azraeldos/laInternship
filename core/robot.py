# Goal: Write a Python program that controls a web browser using Playwright to complete a fixed, single task (e.g., Log in, search for a specific product, and report its price).

# Actions: Your code must perform all necessary browser actions (Go to URL, Click, Type).

# Reliability: The code must include proper error handling so it doesn't crash on slow pages or missing elements.

# Output: The program should print a clear, final result to the console (e.g., "Success! Product ABC found").

from playwright.sync_api import Playwright, sync_playwright, TimeoutError


def run(playwright: Playwright) -> None:
    # Launch browser (set headless=True to hide the window)
    browser = playwright.chromium.launch(headless=False, slow_mo=1000)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Step 1: Go to login page
        print("Opening the login page...")
        #30 second timeout
        page.goto("https://www.saucedemo.com/", timeout=30000)

        # Step 2: Log in
        # Wait for input fields to ensure the page has loaded
        page.wait_for_selector("[data-test='username']", timeout=10000)
        print("Logging in...")
        page.locator("[data-test=\"username\"]").click()
        page.locator("[data-test=\"username\"]").fill("standard_user")
        page.locator("[data-test=\"password\"]").click()
        page.locator("[data-test=\"password\"]").fill("secret_sauce")
        page.locator("[data-test=\"login-button\"]").click()

        # Step 3: Click on a specific product (Sauce Labs Backpack)
        # Wait for product detail elements before reading
        page.wait_for_selector("[data-test='inventory-item-name']", timeout=10000)
        page.wait_for_selector("[data-test='inventory-item-price']", timeout=10000)
        page.locator("[data-test=\"item-4-title-link\"]").click()
        page.locator("[data-test=\"inventory-item-price\"]").click()

        # Step 4: Extract product name and price
        product_name = page.locator("[data-test='inventory-item-name']").inner_text()
        price = page.locator("[data-test='inventory-item-price']").inner_text()

        # Step 5: Print result to console
        print(f"Success! '{product_name}' found at price {price}.")
    except TimeoutError:
        print(" Timeout: Page or element took too long to load.")
    except Exception as e:
        print(f" Error: {e}")
    finally:
        print("Closing browser...")
        # Step 6: Close browser
        context.close()
        browser.close()

# Run the script
if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)