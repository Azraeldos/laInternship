# mcpAI — Folder-specific instructions

This folder contains a FastAPI app and a plan-driven runner. Because the code uses relative paths and subprocess calls, please `cd` into this folder before running the runner or starting the API.

Files of interest
- `app.py` — FastAPI app that exposes an endpoint `/launch` and uses `robotAI.py` to execute instructions.
- `robotAI.py` — the plan runner and Playwright-based step executor. Reads `plan.json` by default.
- `plan.json` — example static plan.
- `tool_schema.json`, `llmInstructions.md` — additional docs.

Setup (inside `mcpAI`)

```bash
# from repo root
cd mcpAI

# use the project venv from repo root (.venv) or create your own
python3 -m venv .venv
source .venv/bin/activate

# install dependencies (from repo root or this folder)
pip install -r ../requirements.txt

# install playwright browsers if runner uses Playwright
python -m playwright install
```

Run `robotAI.py` directly

```bash
cd mcpAI
python robotAI.py
```

Start the FastAPI app

```bash
cd mcpAI
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

API example (after starting uvicorn)

```bash
curl -X POST http://127.0.0.1:8000/launch \
  -H "Content-Type: application/json" \
  -d '{"instruction":"Log into saucedemo.com with username standard_user and password secret_sauce and extract the Backpack name and price","headless":true,"slow_mo":0}'
```

If you want to run uvicorn from repository root without `cd` into `mcpAI`, I can update `app.py` to construct an absolute path to `robotAI.py` (recommended).
