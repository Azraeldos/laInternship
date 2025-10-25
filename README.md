# Quick start

This repository has two runnable parts:

- core: a small script at `core/robot.py`
- mcpAI: a FastAPI app and a plan-runner (`mcpAI/app.py`, `mcpAI/robotAI.py`, `mcpAI/plan.json`)

Minimal setup (one-time, from repo root)

Copy the example below into a new `.env` file at the project root:
```bash
   OPENAI_API_KEY=your_openai_api_key_here
   OPENAI_MODEL=gpt-4o-mini
```

```bash
# create and activate a venv
python3 -m venv .venv
source .venv/bin/activate

# install runtime + dev deps
pip install --upgrade pip
pip install -r requirements.txt
sudo apt  install jq

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
- Plan.json has default output for immeditate testing.
- Install playright mcp server
    https://github.com/microsoft/playwright-mcp (there is a `Install Server VS Code`) button for ease of installation

In terminal
```bash
source .venv/bin/activate
cd mcpAI
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

In another terminal 
```bash
npx @playwright/mcp@latest --port 4375
- Ensure playwright MCP server is runnning
```

In another terminal enter
```bash
 curl -s -X POST http://127.0.0.1:8000/launch   -H "Content-Type: application/json"   -d '{"instruction":"Login to https://www.saucedemo.com and return the Bike Light name and price"}' | jq . 
 ```

Expected output:
```
{
  "goal": "Login to https://www.saucedemo.com and return the Bike Light name and price",
  "extracted": {
    "bike_light_name": "Sauce Labs Bike Light",
    "bike_light_price": "$9.99"
  }
}
```
3. Optional Challenge 2: Making It Shareable (Deployment Skills)

```bash
source .venv/bin/activate
cd mcpAI
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```
- In a new terminal
```bash
npx @playwright/mcp@latest --port 4375
```
- Ensure playwright MCP server is runnning

- In a new terminal
```bash
curl -s -X POST http://127.0.0.1:8000/launch \
  -H "Content-Type: application/json" \
  -d '{"instruction":"Login to https://www.saucedemo.com and return the Backpack name and price"}' \
| jq .
```

Expected output:
```
{
  "goal": "Login to https://www.saucedemo.com and return the Backpack name and price",
  "extracted": {
    "backpack_name": "Sauce Labs Backpack",
    "backpack_price": "$29.99"
  }
}
```
Thank You!