from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess, sys

app = FastAPI(title="Tiny Runner API")

class Payload(BaseModel):
    instruction: str
    headless: bool = True
    slow_mo: int = 0
    timeout_sec: int = 120  # server-side guard

@app.post("/launch")
def launch(p: Payload):
    cmd = [
        sys.executable, "robotAI.py",               # existing runner script
        "--instruction", p.instruction,
        "--headless", "true" if p.headless else "false",
        "--slow-mo", str(p.slow_mo),
    ]
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
