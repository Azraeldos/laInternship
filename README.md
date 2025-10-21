# Quick start

This repository has two runnable parts:

- core: a small script at `core/robot.py`
- mcpAI: a FastAPI app and a plan-runner (`mcpAI/app.py`, `mcpAI/robotAI.py`, `mcpAI/plan.json`)

Minimal setup (one-time, from repo root)

```bash
# create and activate a venv
python3 -m venv .venv
source .venv/bin/activate

# install runtime + dev deps
pip install --upgrade pip
pip install -r requirements.txt

# install Playwright browsers
python -m playwright install
```
1. Required Core: The Robot Driver (Foundational Skills)

Run core script

```bash
python core/robot.py
```
Expected output:
```
Opening the login page...
Logging in...
Success! 'Sauce Labs Backpack' found at price $29.99.
Closing browser...
```

2. Optional Challenge 1: The AI Brain with MCP (Advanced Skills)

**Note**  
- Plan.json has default output for immeditate testing please clear plan.json if you do not wish to use the default plan.
- We use integredated ide AI assistant to avoid fees from LLM api 
- Install playright mcp server
    https://github.com/microsoft/playwright-mcp (there is a `Install Server VS Code`) button for ease of installation
- `mcp.json` can be found in playwright MCP settings configuration JSON
- Ensure playwright MCP server is runnning
```bash
cd mcpAI
```
In copilot agent mode, attach these context files
    `mcpAI/llmInstructions.md && mcpAI/tool_schema.json && mcp.json`
then enter 
"Log into saucedemo.com with the username standard_user and password secret_sauce and get me the name and price of a black Backpack output json to plan.json." 
 (json not able to be correctly copied directly from chat).

 then 
 ```python robotAI.py```

Expected output:
```
Goal: Log into saucedemo.com with standard_user and extract the Backpack name and price
Step 1: navigate {'url': 'https://www.saucedemo.com'}
Step 2: wait_for {'selector': "[data-test='username']", 'state': 'visible'}
Step 3: type {'selector': "[data-test='username']", 'text': 'standard_user', 'clear': True}
Step 4: type {'selector': "[data-test='password']", 'text': 'secret_sauce', 'clear': True}
Step 5: click {'selector': "[data-test='login-button']"}
Step 6: wait_for {'selector': '.inventory_list', 'state': 'visible'}
Step 7: extract_text {'selector': '.inventory_item:has-text("Backpack") .inventory_item_name'}
Step 8: extract_text {'selector': '.inventory_item:has-text("Backpack") .inventory_item_price'}

--- Extracted Values ---
backpack_name: Sauce Labs Backpack
backpack_price: $29.99
Error: '"goal"'
Closing browser...
```
3. Optional Challenge 2: Making It Shareable (Deployment Skills)

```bash
cd mcpAI

uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Example API call (once uvicorn is running)

```bash

curl -X POST http://127.0.0.1:8000/launch \
    -H "Content-Type: application/json" \
    -d  '{"instruction":"Login to saucedemo and return the Backpack name and price","headless":true}'
```
```
Expected output:
```
{"goal":"Login to saucedemo and return the Backpack name and price","extracted":{"backpack_name":"Sauce Labs Backpack","backpack_price":"$29.99"}}
```