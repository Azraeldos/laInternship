# Purpose: FastAPI server that accepts a plain-English instruction,
# asks the LLM to generate a Playwright action plan (plan.json),
# executes it using robotAI.py, and returns structured extraction results.

import json, re, subprocess, sys
from pathlib import Path
from typing import Dict, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llmPlan import generate_plan

app = FastAPI(title="Tiny Runner API")

# Request body for the /launch endpoint.
class Payload(BaseModel):
    instruction: str
    timeout_sec: int = 120  # server-side guard

# Internal helpers (readability only)
# Execute robotAI.py as a subprocess.
# Returns:
#     (returncode, stdout, stderr)
# Raises:
#     HTTPException(504) if the subprocess times out.

def _run_robot_runner(timeout_sec: int) -> Tuple[int, str, str]:
    runner = Path(__file__).with_name("robotAI.py")
    cmd = [sys.executable, str(runner)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        # Keep behavior identical: surface a 504 on timeout
        raise HTTPException(status_code=504, detail="Runner timed out")

# Scan stdout for a prefixed error line ("Error: ...") from the runner logs.
# Returns the raw error message (without the 'Error:' prefix) or None.
def _extract_error_line(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.strip().startswith("Error:"):
            return line.strip()[len("Error:"):].strip()
    return None

# Prefer a JSON object printed by robotAI.py containing {"extracted": {...}}.
# Falls back to {} if none found or malformed.
def _parse_json_tail(stdout: str) -> Dict[str, str]:
    candidates = re.findall(r"\{.*\}", stdout, flags=re.DOTALL)
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict) and isinstance(obj.get("extracted"), dict):
                return obj["extracted"]
        except Exception:
            # keep scanning
            pass
    return {}

# Fallback: collect 'key: value' lines from stdout.
# We intentionally avoid lines that look like stack traces or control logs.
def _fallback_key_values(stdout: str) -> Dict[str, str]:
    extracted: Dict[str, str] = {}
    for line in stdout.splitlines():
        raw = line.strip()
        if not raw or ":" not in raw:
            continue
        key, val = raw.split(":", 1)
        key, val = key.strip(), val.strip()
        # Ignore control/log keys
        if key.lower().startswith(("step", "goal", "error", "call log")):
            continue
        if key.lower() in {"closing browser", "extracted values"}:
            continue
        # Only accept sane keys to avoid picking up stack frames etc.
        if not re.match(r"^[A-Za-z0-9_]+$", key):
            continue
        extracted[key] = val
    return extracted

# API
# Create a plan from the user's instruction, execute it,
# and return structured extraction results with a small log tail.
# Returns:
#      JSON payload: { goal, extracted, full_log, [error] }
@app.post("/launch")
def launch(p: Payload):
    #1 Generate a fresh plan.json for the given instruction
    try:
        generate_plan(p.instruction)
    except Exception as e:
        # Preserve behavior: report plan generation failures as 400
        raise HTTPException(status_code=400, detail=f"Plan generation failed: {e}")
    #2 Execute the robot runner that reads and executes plan.json
    returncode, stdout, stderr = _run_robot_runner(timeout_sec=p.timeout_sec)
    if returncode != 0:
        # Preserve behavior: Include stderr if present
        raise HTTPException(status_code=500, detail=stderr.strip() or "Runner error")
    #3 Check for a runner-signaled error line in the logs
    error_msg = _extract_error_line(stdout)
    #4 Prefer a well-formed JSON final_report printed by robotAI.py
    extracted = _parse_json_tail(stdout)
    #5 Fallback to collecting "key: value" lines from stdout
    if not extracted:
        extracted = _fallback_key_values(stdout)
    #6 Return structured result (include a small tail of stdout for debugging)
    result = {
        "goal": p.instruction,
        "extracted": extracted
        # "full_log": stdout,
    }
    if error_msg and not extracted:
        result["error"] = error_msg

    return result
