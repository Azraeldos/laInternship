from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess, sys
from llmPlan import generate_plan  # NEW
from pathlib import Path


app = FastAPI(title="Tiny Runner API")

class Payload(BaseModel):
    instruction: str
    headless: bool = True
    slow_mo: int = 0
    timeout_sec: int = 120  # server-side guard

@app.post("/launch")
def launch(p: Payload):
    # 
    # 1) Ask the LLM for a plan.json (writes mcpAI/plan.json)
    try:
        generate_plan(p.instruction)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Plan generation failed: {e}")

    # 2) Run your existing runner (unchanged)
    runner = Path(__file__).with_name("robotAI.py")
    cmd = [sys.executable, str(runner)]
    # 
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=p.timeout_sec
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Runner timed out")

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=proc.stderr.strip() or "Runner error")
 
    stdout = proc.stdout

    # --- simple text parser for runner output ---
    def grab(label: str):
        for line in stdout.splitlines():
            if line.startswith(label + ":"):
                return line.split(":", 1)[1].strip()
        return None

    parsed = {
        "goal": p.instruction,
        "extracted": {
            "backpack_name": grab("backpack_name"),
            "backpack_price": grab("backpack_price"),
        }
    }

    return parsed
