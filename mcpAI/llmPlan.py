# mcpAI/llm_plan.py
# Purpose: Call OpenAI to produce a strict JSON action plan (plan.json) using your existing
# schema (tool_schema.json) and instructions (llmInstructions.md).

import json
from pathlib import Path
from dotenv import load_dotenv
import os
from openai import OpenAI
import requests
from jsonschema import validate as jsonschema_validate, ValidationError

ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_PATH = ROOT / "llmInstructions.md"
SCHEMA_PATH = ROOT / "toolSchema.json"
PLAN_PATH = ROOT / "plan.json"


def fetch_mcp_snapshot(mcp_url="http://127.0.0.1:4173/snapshot", session_id=None):
    """Fetch a JSON snapshot from a running Playwright MCP server.

    The MCP server URL can be customized via the MCP_SNAPSHOT_URL env var.
    Return a dict (parsed JSON) or raise on network errors.
    """
    params = {}
    if session_id:
        params["session"] = session_id
    r = requests.get(mcp_url, params=params, timeout=5)
    r.raise_for_status()
    return r.json()

#NEW
def _summarize_snapshot(snapshot, max_nodes=100):
    """Return a shallow, compact summary of the MCP snapshot.

    We keep this simple: collect up to `max_nodes` nodes that include a role/name and
    any common selector-like attributes (id, class, data-test*). The summary is
    intentionally shallow to avoid huge prompts.
    """
    if not snapshot:
        return {"error": "no snapshot"}

    nodes = []

    def collect(node):
        if not isinstance(node, dict) or len(nodes) >= max_nodes:
            return
        entry = {}
        for k in ("role", "name"):
            v = node.get(k)
            if v:
                entry[k] = v
        attrs = {}
        # shallow attribute containers
        if isinstance(node.get("attributes"), dict):
            for key, val in node["attributes"].items():
                if key.startswith("data-") and val:
                    attrs[key] = val
        # common top-level attrs
        for key in ("id", "class"):
            v = node.get(key)
            if v:
                attrs[key] = v
        if attrs:
            entry["attrs"] = attrs
        if entry:
            nodes.append(entry)

        # shallow children
        for child_key in ("children", "nodes"):
            for child in node.get(child_key, []) or []:
                collect(child)
                if len(nodes) >= max_nodes:
                    return

    if isinstance(snapshot, dict):
        collect(snapshot)
    elif isinstance(snapshot, list):
        for item in snapshot:
            collect(item)
            if len(nodes) >= max_nodes:
                break

    return {"nodes": nodes}
#
def generate_plan(goal: str) -> dict:
    """
    Ask the LLM for a JSON plan that adheres to the schema and your instructions.
    Returns the parsed dict and writes it to plan.json.
    """
    
    load_dotenv()  # loads OPENAI_API_KEY, OPENAI_MODEL
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing. Set it in .env")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Read constraints you already have in the repo
    llm_instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    json_schema = SCHEMA_PATH.read_text(encoding="utf-8")

    client = OpenAI(api_key=api_key)

    # We ask for pure JSON via response_format, and we hard-pin the contract in the prompt.
    system = (
        "You are a planning engine that outputs a Playwright action plan for a Python runner.\n"
        "Output ONLY a single JSON object that validates against the provided JSON Schema.\n"
        "Do not include markdown, code fences, or explanations."
    )

    user = f"""\

Goal:
{goal}

Instructions (verbatim from llmInstructions.md):
{llm_instructions}

JSON Schema (verbatim from tool_schema.json):
{json_schema}

Output: A SINGLE JSON object that strictly follows the schema and the instruction rules.
"""
# NEW
    # Try to fetch a live MCP snapshot and append a concise summary to the prompt.
    mcp_url = os.getenv("MCP_SNAPSHOT_URL", "http://127.0.0.1:4173/snapshot")
    try:
        raw_snapshot = fetch_mcp_snapshot(mcp_url=mcp_url)
    except Exception as e:
        raw_snapshot = {"error": f"Could not fetch MCP snapshot: {e}"}

    try:
        snapshot_summary = _summarize_snapshot(raw_snapshot)
        user += "\n\nMCP_SNAPSHOT_SUMMARY:\n" + json.dumps(snapshot_summary, indent=2)
    except Exception:
        user += "\n\nMCP_SNAPSHOT_SUMMARY: {\"error\": \"snapshot processing failed\"}"
#
    # New-style responses with JSON enforced
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    raw = resp.choices[0].message.content
    plan = json.loads(raw)  # enforce parse; fail fast if not JSON

    # Minimal sanity check for required keys
    if "goal" not in plan or "steps" not in plan:
        raise ValueError("Plan missing required keys ('goal', 'steps').")

    # Validate plan against the provided JSON schema (fail fast if invalid)
    try:
        schema_obj = json.loads(json_schema)
        jsonschema_validate(instance=plan, schema=schema_obj)
    except ValidationError as ve:
        raise ValueError(f"Plan failed JSON Schema validation: {ve}")
    except Exception as e:
        # If schema can't be parsed or other issue, raise to avoid writing a bad plan
        raise RuntimeError(f"Schema validation error: {e}")

    PLAN_PATH.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan

if __name__ == "__main__":
    # small manual test
    print("Writing plan.json for a demo goal...")
    demo_goal = "Login to saucedemo and return the Backpack name and price"
    out = generate_plan(demo_goal)
    print(json.dumps(out, indent=2))
