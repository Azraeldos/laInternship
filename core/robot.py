# Goal: Write a Python program that controls a web browser using Playwright to complete a fixed, single task (e.g., Log in, search for a specific product, and report its price).

# Actions: Your code must perform all necessary browser actions (Go to URL, Click, Type).

# Reliability: The code must include proper error handling so it doesn't crash on slow pages or missing elements.

# Output: The program should print a clear, final result to the console (e.g., "Success! Product ABC found").

from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    # Launch browser (set headless=True to hide the window)
    browser = playwright.chromium.launch(headless=False, slow_mo=200)
    context = browser.new_context()
    page = context.new_page()
     # Step 1: Go to login page
    page.goto("https://www.saucedemo.com/")
    # Step 2: Log in
    page.locator("[data-test=\"username\"]").click()
    page.locator("[data-test=\"username\"]").fill("standard_user")
    page.locator("[data-test=\"password\"]").click()
    page.locator("[data-test=\"password\"]").fill("secret_sauce")
    page.locator("[data-test=\"login-button\"]").click()
    # Step 4: Click on a specific product (Sauce Labs Backpack)
    page.locator("[data-test=\"item-4-title-link\"]").click()
    page.locator("[data-test=\"inventory-item-price\"]").click()
    # Step 5: Extract product name and price
    product_name = page.locator("[data-test='inventory-item-name']").inner_text()
    price = page.locator("[data-test='inventory-item-price']").inner_text()
    # Step 6: Print result to console
    print(f"Success! '{product_name}' found at price {price}.")
    # ---------------------
    # Step 7: Close browser
    context.close()
    browser.close()

# Run the script
with sync_playwright() as playwright:
    run(playwright)