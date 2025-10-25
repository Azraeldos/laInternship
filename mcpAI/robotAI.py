# Purpose: Execute the AI-generated plan.json produced by llmPlan.py.
# Uses Playwright-native selectors and .filter(has_text=...) for robust text targeting,
# and always prints a final JSON summary the API can parse.

import json, re, sys
from pathlib import Path
from typing import Dict, Optional
from playwright.sync_api import Playwright, TimeoutError, sync_playwright

DEFAULT_TIMEOUT = 30000  # ms
DEFAULT_PLAN_PATH = "plan.json"

# Plan loading (robust)
# Load and minimally validate the plan JSON file.
# Exits the process with code 2 on any validation error to keep behavior consistent.
def load_plan_or_die(plan_path: str) -> dict:
    p = Path(plan_path)
    if not p.exists():
        print(f"Error: plan file not found at {p.resolve()}", file=sys.stderr)
        sys.exit(2)
    raw = p.read_text(encoding="utf-8")
    if not raw.strip():
        print(f"Error: plan file is empty at {p.resolve()}", file=sys.stderr)
        sys.exit(2)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: plan file is not valid JSON ({e}) at {p.resolve()}", file=sys.stderr)
        sys.exit(2)
    # minimal sanity checks
    if not isinstance(plan, dict) or "steps" not in plan or not isinstance(plan["steps"], list):
        print(f"Error: plan JSON missing required 'steps' array at {p.resolve()}", file=sys.stderr)
        sys.exit(2)
    return plan

# Selector helpers
# Extract the first text fragment from :has-text("...") OR :has-text('...')
# and also supports legacy :contains('...') / :contains("...").
# Returns the inner text, or None if not present.
def _text_from_selector(selector: str) -> Optional[str]:
    m = re.search(r':has-text\((["\'])(.*?)\1\)', selector)
    if m:
        return m.group(2)
    m2 = re.search(r':contains\((["\'])(.*?)\1\)', selector)
    if m2:
        return m2.group(2)
    return None

# Replace :contains('...') with :has-text("...") for CSS compatibility.
def _replace_contains(selector: str) -> str:
    def _repl(m: re.Match) -> str:
        text = m.group(2).replace('"', '\\"')
        return f':has-text("{text}")'
    return re.sub(r":contains\((['\"])(.*?)\1\)", _repl, selector)

# If selector targets SauceDemo product cards and has nested :has(...:has-text("X")...),
# flatten to `.inventory_item:has-text("X") .inventory_item_name|price`.
def _flatten_inventory_selector(selector: str) -> str:
    sel = _replace_contains(selector)
    txt = _text_from_selector(sel)
    if txt and ".inventory_item" in sel:
        wants_name = ".inventory_item_name" in sel or re.search(r"\bname\b", sel)
        wants_price = ".inventory_item_price" in sel or re.search(r"\bprice\b", sel)
        if wants_name or wants_price:
            simplified = f'.inventory_item:has-text("{txt}") ' + (
                ".inventory_item_name" if wants_name else ".inventory_item_price"
            )
            if sel != simplified:
                print(f"[selector flattened] from: {sel}  ->  to: {simplified}")
            return simplified
    return sel

# Normalization pipeline for CSS selectors (no behavior change).
def _normalize(selector: str) -> str:
    after = _flatten_inventory_selector(selector)
    if selector != after:
        print(f"[selector normalized] from: {selector}  ->  to: {after}")
    return after

# Playwright helpers
# Best-effort text extraction using Playwright-native filters:
# - If the selector references a product card with a text fragment, use:
#     page.locator(".inventory_item").filter(has_text=fragment)
# then scope to a child (name/price) if indicated.
# - Otherwise, use the normalized selector directly.

def _get_text_with_playwright_filters(page, selector: str) -> str:
    norm = _normalize(selector)
    frag = _text_from_selector(norm)
    # Prefer Playwright-native filtering for product cards
    if frag and ".inventory_item" in norm:
        wants_name = "inventory_item_name" in norm or re.search(r"\bname\b", norm)
        wants_price = "inventory_item_price" in norm or re.search(r"\bprice\b", norm)
        base = page.locator(".inventory_item").filter(has_text=frag)
        target = (
            base.locator(".inventory_item_name") if wants_name
            else base.locator(".inventory_item_price") if wants_price
            else base
        )
        target.first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        return target.first.inner_text()
    # Fallback: normalized CSS directly
    loc = page.locator(norm)
    loc.first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
    return loc.first.inner_text()

# Runner core
# Back-compat id retrieval:
#   - Prefer step-level 'id'
#   - Otherwise accept args['id'] (some plans put id under args)

def _get_step_id(step: dict) -> Optional[str]:
    if "id" in step:
        return step["id"]
    args = step.get("args", {})
    if isinstance(args, dict) and "id" in args:
        return args["id"]
    return None
# Execute a single plan step against the Playwright page.
#    Returns:
#         For extract_text: the extracted string.
#         Otherwise: None.
def run_step(page, step: dict, extracted: Dict[str, str]) -> Optional[str]:
    tool = step["tool"]
    args = step.get("args", {})
    if tool == "navigate":
        url = args["url"]
        page.goto(url, timeout=DEFAULT_TIMEOUT)
        return None
    if tool == "click":
        selector = _normalize(args["selector"])
        loc = page.locator(selector)
        loc.first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        loc.first.click()
        return None
    if tool == "type":
        selector = _normalize(args["selector"])
        text = args.get("text", "")
        clear = args.get("clear", True)
        loc = page.locator(selector)
        loc.first.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        if clear:
            loc.fill(text)
        else:
            loc.type(text)
        return None
    if tool == "wait_for":
        selector = _normalize(args["selector"])
        state = args.get("state", "visible")
        page.locator(selector).first.wait_for(state=state, timeout=DEFAULT_TIMEOUT)
        return None
    if tool == "extract_text":
        selector = args["selector"]
        return _get_text_with_playwright_filters(page, selector)
    print(f"Skipping unknown tool: {tool}")
    return None
#  Run all steps defined in the given plan.json file and print a final JSON summary.
#     Behavior preserved:
#       - Launches browser with headless=False and slow_mo=500
#       - Prints per-step logs and captures values by id (step-level or args['id'])
#       - Emits either the plan-provided JSON final_report or a fallback JSON
def execute_plan(playwright: Playwright, plan_path: str = DEFAULT_PLAN_PATH) -> None:
    plan = load_plan_or_die(plan_path)
    browser = playwright.chromium.launch(headless=False, slow_mo=500)
    context = browser.new_context()
    page = context.new_page()
    extracted: Dict[str, str] = {}
    had_error = False
    error_message: Optional[str] = None
    try:
        print(f"Goal: {plan.get('goal','(none)')}")
        for i, step in enumerate(plan["steps"], start=1):
            print(f"Step {i}: {step['tool']} {step.get('args', {})}")
            try:
                result = run_step(page, step, extracted)
                # --- CAPTURE: accept id on step or under args
                step_id = _get_step_id(step)
                if step["tool"] == "extract_text" and step_id:
                    extracted[step_id] = "" if result is None else str(result)
                    print(f"[captured] {step_id} = {extracted[step_id]!r}")
            except TimeoutError as e:
                had_error = True
                error_message = f"Timeout: {e}"
                print(f"Error: {error_message}")
                break
            except Exception as e:
                had_error = True
                error_message = str(e)
                print(f"Error: {error_message}")
                break
        # --- Reporting ---
        final_report = plan.get("final_report")
        if extracted:
            print("\n--- Extracted Values ---")
            for key, value in extracted.items():
                print(f"{key}: {value}")
        # Try to print plan-provided JSON template
        printed_json = False
        if isinstance(final_report, str) and final_report.strip():
            try:
                out = final_report.format(**extracted)
                import json as _json
                _json.loads(out)  # validate
                print(out)
                printed_json = True
            except Exception:
                # fall through to default JSON
                pass
        # Fallback: always print valid JSON
        if not printed_json:
            import json as _json
            payload = {"goal": plan.get("goal"), "extracted": extracted}
            if had_error and error_message and not extracted:
                payload["error"] = error_message
            print(_json.dumps(payload, ensure_ascii=False))
    finally:
        print("Closing browser...")
        context.close()
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as pw:
        # Optional: allow overriding plan path via CLI: python robotAI.py my_plan.json
        plan_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PLAN_PATH
        execute_plan(pw, plan_path)
