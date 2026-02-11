# Purpose: Produce a strict JSON Playwright plan (plan.json) with TRUE MCP integration (SSE),
# falling back to a Playwright DOM summary if MCP is unavailable.

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from jsonschema import validate as jsonschema_validate, ValidationError
from openai import OpenAI
from playwright.sync_api import sync_playwright

# Official Python MCP client (SSE transport is ASYNC)
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

from config import config
from logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Paths & constants
ROOT = Path(__file__).resolve().parent
INSTRUCTIONS_PATH = ROOT / "llmInstructions.md"
SCHEMA_PATH = ROOT / "toolSchema.json"
PLAN_PATH = ROOT / "plan.json"
DEFAULT_MAX_NODES = 120


# Basic file utilities

# Read a UTF-8 text file path into a single string
def _read_text(p: Path) -> str:
    """Read text file."""
    return p.read_text(encoding="utf-8")


# Read a UTF-8 JSON file path and parse it
def _read_json(p: Path) -> Any:
    """Read JSON file."""
    return json.loads(p.read_text(encoding="utf-8"))


# MCP (SSE) INTEGRATION
# Connect to a Playwright MCP server via SSE, list tools, pick a snapshot-like tool, call it, and return JSON.
#     Returns:
#         A dict-like snapshot payload or {"error": "..."} on failure.
async def _grab_snapshot_from_mcp_async(url: str) -> Dict[str, Any]:
    """Grab snapshot from MCP server."""
    try:
        async with sse_client(url=url) as (read, write):
            async with ClientSession(read, write) as session:
                # handshake
                await session.initialize()
                # discover tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                # pick a "snapshot"-like tool
                preferred = ("snapshot", "pageSnapshot", "accessibilitySnapshot", "getPageSnapshot")
                chosen = next((t for t in preferred if t in tool_names), None)
                if not chosen:
                    matches = [t for t in tool_names if "snapshot" in t.lower()]
                    if not matches:
                        return {"error": "no snapshot-like tool found on MCP server"}
                    chosen = matches[0]
                # call the tool
                result = await session.call_tool(chosen, arguments={})
                # parse the response content for JSON
                # (result.content is a list of content parts)
                for part in result.content:
                    # application/json
                    if getattr(part, "type", "") == "application/json":
                        data = getattr(part, "data", None)
                        if isinstance(data, dict):
                            return data
                        if isinstance(data, list):
                            return {"nodes": data}
                    # text/plain that might contain JSON
                    if getattr(part, "type", "") == "text/plain":
                        text = getattr(part, "text", "")
                        if isinstance(text, str) and text.strip():
                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, dict):
                                    return parsed
                                if isinstance(parsed, list):
                                    return {"nodes": parsed}
                            except Exception:
                                # not JSON; keep scanning
                                pass
                return {"error": "snapshot tool returned no usable JSON"}
    except Exception as e:
        logger.error(f"MCP snapshot failed: {e}", exc_info=True)
        return {"error": f"mcp sse failed: {e}"}


# Synchronous wrapper around the async SSE client call (keeps surface unchanged)
def _get_mcp_snapshot_sync(url: str) -> Dict[str, Any]:
    """Get MCP snapshot synchronously."""
    try:
        return asyncio.run(_grab_snapshot_from_mcp_async(url))
    except Exception as e:
        logger.error(f"MCP snapshot sync wrapper failed: {e}", exc_info=True)
        return {"error": f"mcp sse failed: {e}"}


# Compact the MCP snapshot into a shallow list of nodes with role/name/attrs.
# This keeps the LLM prompt small but useful.
#     Returns:
#         {"nodes": [...]} or {"error": "..."}.
def _summarize_snapshot(snapshot: Any, max_nodes: int = DEFAULT_MAX_NODES) -> Dict[str, Any]:
    """Summarize MCP snapshot."""
    if not snapshot:
        return {"error": "no snapshot"}
    nodes: List[Dict[str, Any]] = []
    
    def collect(node: Any) -> None:
        if not isinstance(node, dict) or len(nodes) >= max_nodes:
            return
        entry: Dict[str, Any] = {}
        # Common a11y fields
        role = node.get("role")
        name = node.get("name")
        if role:
            entry["role"] = role
        if name:
            entry["name"] = name
        # Useful attrs for selectors / targeting
        attrs: Dict[str, Any] = {}
        if isinstance(node.get("attributes"), dict):
            for key, val in node["attributes"].items():
                # keep data-* for targeting, plus id/class if present
                if key.startswith("data-") and val:
                    attrs[key] = val
        for k in ("id", "class"):
            v = node.get(k)
            if v:
                attrs[k] = v
        if attrs:
            entry["attrs"] = attrs
        if entry:
            nodes.append(entry)
        # shallow traversal across common child containers
        for child_key in ("children", "nodes"):
            children = node.get(child_key) or []
            if isinstance(children, list):
                for child in children:
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
    
    logger.debug(f"Summarized snapshot: {len(nodes)} nodes")
    return {"nodes": nodes}


# Playwright fallback summary
# Extract the first URL in the goal; otherwise use START_URL from the environment
def _pick_url_from_goal_or_env(goal: str) -> Optional[str]:
    """Pick URL from goal or environment."""
    m = re.search(r"https?://\S+", goal)
    if m:
        return m.group(0).rstrip(".,)")
    return os.getenv("START_URL")


# Fallback if MCP server isn't available
# If MCP snapshot is unavailable, open a URL inferred from the goal (or START_URL)
# and collect a compact DOM summary, so the LLM still has some structured data about the page to reason from.
def _playwright_fallback_snapshot(goal: str, max_nodes: int = DEFAULT_MAX_NODES) -> Dict[str, Any]:
    """Fallback snapshot using Playwright."""
    url = _pick_url_from_goal_or_env(goal)
    if not url:
        logger.warning("No URL found in goal or START_URL")
        return {"error": "no URL found (include a URL in the goal or set START_URL)"}
    try:
        logger.info(f"Using Playwright fallback snapshot for: {url}")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            summary = page.evaluate(
                """(limit) => {
                  const out = [];
                  const els = Array.from(document.querySelectorAll('*'));
                  for (const el of els) {
                    const entry = {};
                    const role = el.getAttribute('role');
                    const id = el.id || null;
                    const cls = el.className || null;
                    const attrs = {};
                    for (const a of el.getAttributeNames()) {
                      if (a.startsWith('data-')) attrs[a] = el.getAttribute(a);
                    }
                    const text = (el.textContent || '').trim();
                    const name = text ? text.slice(0, 80) : '';

                    if (role) entry.role = role;
                    if (name) entry.name = name;

                    const bag = {};
                    if (id) bag.id = id;
                    if (cls) bag.class = cls;
                    for (const [k,v] of Object.entries(attrs)) bag[k] = v;
                    if (Object.keys(bag).length) entry.attrs = bag;

                    if (Object.keys(entry).length) out.push(entry);
                    if (out.length >= limit) break;
                  }
                  return { url: location.href, nodes: out };
                }""",
                max_nodes,
            )
            browser.close()
            logger.info(f"Playwright fallback snapshot completed: {len(summary.get('nodes', []))} nodes")
            return summary
    except Exception as e:
        logger.error(f"Playwright fallback failed: {e}", exc_info=True)
        return {"error": f"playwright fallback failed: {e}"}


# Planner (LLM)
#   Ask the LLM for a JSON plan adhering to toolSchema.json + llmInstructions.md.
#     Flow:
#       1) Try TRUE MCP snapshot via SSE.
#       2) If that fails, use Playwright fallback summary.
#       3) Validate and write plan.json.
#     Returns:
#         The validated plan dictionary.
#     Raises:
#         RuntimeError if OPENAI_API_KEY is missing.
#         ValueError if JSON Schema validation fails.
def generate_plan(goal: str) -> dict:
    """Generate plan from goal using LLM."""
    load_dotenv()
    
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing. Set it in your environment or .env")
    
    llm_instructions = _read_text(INSTRUCTIONS_PATH)
    schema_obj = _read_json(SCHEMA_PATH)
    
    # Try MCP snapshot first; fall back to Playwright DOM summary
    source_tag = "MCP_SNAPSHOT_SUMMARY"
    logger.info(f"Attempting MCP snapshot from: {config.MCP_SSE_URL}")
    snapshot = _get_mcp_snapshot_sync(config.MCP_SSE_URL)
    
    if "error" in snapshot:
        logger.warning(f"MCP snapshot failed, using Playwright fallback: {snapshot.get('error')}")
        source_tag = "PLAYWRIGHT_FALLBACK_SUMMARY"
        snapshot_block = _playwright_fallback_snapshot(goal)
    else:
        snapshot_block = _summarize_snapshot(snapshot)
    
    # LLM call with JSON-only response
    system_prompt = (
        "You are a planning engine that outputs a Playwright action plan for a Python runner.\n"
        "Output ONLY a single JSON object that validates against the provided JSON Schema.\n"
        "Do not include markdown, code fences, or explanations."
    )
    user_payload = {
        "goal": goal,
        "instructions_md": llm_instructions,
        "json_schema": schema_obj,
        source_tag: snapshot_block,
    }
    
    logger.info(f"Calling OpenAI API (model: {config.OPENAI_MODEL})")
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    
    try:
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, indent=2)},
            ],
        )
        raw = resp.choices[0].message.content
        plan = json.loads(raw)  # fail fast if not JSON
        
        # Validate against schema
        try:
            jsonschema_validate(instance=plan, schema=schema_obj)
            logger.info("Plan validated successfully against schema")
        except ValidationError as ve:
            logger.error(f"Plan validation failed: {ve}")
            raise ValueError(f"Plan failed JSON Schema validation: {ve}")
        
        # Write plan.json
        PLAN_PATH.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        logger.info(f"Plan written to {PLAN_PATH}")
        return plan
    
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    demo_goal = os.getenv(
        "GOAL",
        "Login to https://www.saucedemo.com and return the Backpack name and price",
    )
    out = generate_plan(demo_goal)
    print(json.dumps(out, indent=2))
