# Goal: Redesign the program so that the execution steps are determined dynamically by an AI Language Model (LLM).

# The Model Context Protocol (MCP): To make the AI smarter and more reliable, you must integrate your solution with the Playwright MCP Server. This server will act as the crucial link that feeds the LLM detailed, structured information about the current state of the webpage (like accessibility data and element roles), allowing the AI to choose the best next action.

# The AI's Role:

# The user provides a plain English goal (e.g., "Buy the cheapest blue shirt on this site.").

# Your code uses the MCP to give the LLM the necessary tools and page context.

# The LLM generates a step-by-step plan using structured commands (like JSON) based on the current page's elements provided by the MCP.

# Execution: Your program reads the AI's plan and executes the steps using your Playwright automation code.

import json
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, TimeoutError


DEFAULT_TIMEOUT = 30000

def run_step(page, step):
    tool = step["tool"]
    args = step.get("args", {})

    if tool == "navigate":
        url = args["url"]
        page.goto(url, timeout=DEFAULT_TIMEOUT)

    elif tool == "click":
        selector = args["selector"]
        page.wait_for_selector(selector, timeout=DEFAULT_TIMEOUT)
        page.locator(selector).click()

    elif tool == "type":
        selector = args["selector"]
        text = args.get("text", "")
        clear = args.get("clear", True)
        page.wait_for_selector(selector, timeout=DEFAULT_TIMEOUT)
        loc = page.locator(selector)
        if clear:
            loc.fill(text)
        else:
            loc.type(text)

    elif tool == "wait_for":
        selector = args["selector"]
        state = args.get("state", "visible")
        page.wait_for_selector(selector, state=state, timeout=DEFAULT_TIMEOUT)

    elif tool == "extract_text":
        selector = args["selector"]
        page.wait_for_selector(selector, timeout=DEFAULT_TIMEOUT)
        return page.locator(selector).inner_text()

    else:
        print(f"Skipping unknown tool: {tool}")

def execute_plan(playwright: Playwright, plan_path: str = "plan.json") -> None:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))

    browser = playwright.chromium.launch(headless=False, slow_mo=500)
    context = browser.new_context()
    page = context.new_page()

    extracted = {}
    try:
        print(f"Goal: {plan.get('goal','(none)')}")
        for i, step in enumerate(plan["steps"], start=1):
            print(f"Step {i}: {step['tool']} {step.get('args',{})}")
            result = run_step(page, step)
            # capture named results if the step includes an id
            if step["tool"] == "extract_text" and "id" in step:
                extracted[step["id"]] = result

        # Report
        final_report = plan.get("final_report")
        # Always print extracted results to console
        if extracted:
            print("\n--- Extracted Values ---")
            for key, value in extracted.items():
                print(f"{key}: {value}")
        if isinstance(final_report, str):
            print(final_report.format(**extracted))
        else:
            print("Success! Plan executed.")
    except TimeoutError:
        print("Timeout: Page or element took too long to load.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Closing browser...")
        context.close()
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as pw:
        execute_plan(pw)
