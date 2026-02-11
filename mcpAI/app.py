"""FastAPI server that accepts a plain-English instruction,
asks the LLM to generate a Playwright action plan (plan.json),
executes it using robotAI.py, and returns structured extraction results.
"""

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import config
from exceptions import AuthenticationError, ValidationError, PlanGenerationError, RunnerError
from logging_config import setup_logging, get_logger
from llmPlan import generate_plan

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Tiny Runner API",
    description="AI-powered web automation API using Playwright",
    version="1.0.0",
)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS if "*" not in config.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Validate configuration on startup
@app.on_event("startup")
async def startup_event():
    """Validate configuration on startup."""
    try:
        config.validate()
        logger.info("Configuration validated successfully")
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise


# Authentication dependency
async def verify_api_key(x_api_key: str = Header(..., description="API key for authentication")):
    """Verify API key from request header."""
    if not config.API_KEYS:
        logger.warning("No API keys configured - authentication disabled")
        return x_api_key
    
    if x_api_key not in config.API_KEYS:
        logger.warning(f"Invalid API key attempted: {x_api_key[:8]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return x_api_key


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests for tracing."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Add request ID to logger context
    logger.info(f"Request started: {request.method} {request.url.path}", extra={"request_id": request_id})
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# URL validation helper
def validate_url(url: str) -> bool:
    """Validate URL against allowed patterns to prevent SSRF."""
    if not config.ALLOWED_URL_PATTERNS:
        # If no patterns configured, allow all HTTPS URLs
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https")
    
    for pattern in config.ALLOWED_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    
    return False


def sanitize_instruction(instruction: str) -> str:
    """Sanitize instruction text to remove dangerous characters."""
    # Remove null bytes and control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", instruction)
    # Limit length
    max_length = 5000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"Instruction truncated to {max_length} characters")
    return sanitized


# Request body for the /launch endpoint
class Payload(BaseModel):
    """Request payload for the launch endpoint."""
    
    instruction: str
    timeout_sec: int = 120  # server-side guard
    
    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, v: str) -> str:
        """Validate and sanitize instruction."""
        if not v or not v.strip():
            raise ValueError("Instruction cannot be empty")
        
        sanitized = sanitize_instruction(v)
        
        # Extract URLs from instruction
        url_pattern = r"https?://[^\s<>\"']+"
        urls = re.findall(url_pattern, sanitized)
        
        for url in urls:
            if not validate_url(url):
                raise ValueError(f"URL not allowed: {url}")
        
        return sanitized
    
    @field_validator("timeout_sec")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout value."""
        if v < 1 or v > 600:
            raise ValueError("Timeout must be between 1 and 600 seconds")
        return v


# Internal helpers
def _run_robot_runner(timeout_sec: int, request_id: str) -> Tuple[int, str, str]:
    """Execute robotAI.py as a subprocess.
    
    Returns:
        (returncode, stdout, stderr)
    Raises:
        HTTPException(504) if the subprocess times out.
    """
    runner = Path(__file__).with_name("robotAI.py")
    cmd = [sys.executable, str(runner)]
    try:
        logger.info(f"Starting robot runner (timeout: {timeout_sec}s)", extra={"request_id": request_id})
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        logger.info(f"Robot runner completed with return code {proc.returncode}", extra={"request_id": request_id})
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        logger.error(f"Robot runner timed out after {timeout_sec}s", extra={"request_id": request_id})
        raise HTTPException(status_code=504, detail="Runner timed out")


def _extract_error_line(stdout: str) -> str | None:
    """Scan stdout for a prefixed error line ("Error: ...") from the runner logs.
    
    Returns the raw error message (without the 'Error:' prefix) or None.
    """
    for line in stdout.splitlines():
        if line.strip().startswith("Error:"):
            return line.strip()[len("Error:"):].strip()
    return None


def _parse_json_tail(stdout: str) -> Dict[str, str]:
    """Prefer a JSON object printed by robotAI.py containing {"extracted": {...}}.
    
    Falls back to {} if none found or malformed.
    """
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


def _fallback_key_values(stdout: str) -> Dict[str, str]:
    """Fallback: collect 'key: value' lines from stdout.
    
    We intentionally avoid lines that look like stack traces or control logs.
    """
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


# Error handlers
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """Handle authentication errors."""
    logger.warning(f"Authentication failed: {exc}", extra={"request_id": getattr(request.state, "request_id", None)})
    return JSONResponse(
        status_code=401,
        content={"error": "Authentication failed", "detail": "Invalid API key"},
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors."""
    logger.warning(f"Validation failed: {exc}", extra={"request_id": getattr(request.state, "request_id", None)})
    return JSONResponse(
        status_code=400,
        content={"error": "Validation failed", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with sanitized error messages."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(f"Unhandled exception: {exc}", exc_info=True, extra={"request_id": request_id})
    
    # Don't leak sensitive information in production
    if config.ENVIRONMENT == "production":
        detail = "An internal error occurred"
    else:
        detail = str(exc)
    
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": detail},
    )


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint.
    
    Returns:
        JSON payload with status and checks for API, OpenAI, and MCP server.
    """
    checks = {
        "api": "healthy",
        "openai": "unknown",
        "mcp_server": "unknown",
    }
    
    # Check OpenAI connectivity
    try:
        if config.OPENAI_API_KEY:
            # Simple check - try to create a client (doesn't make actual API call)
            checks["openai"] = "configured"
        else:
            checks["openai"] = "not_configured"
    except Exception as e:
        logger.error(f"OpenAI check failed: {e}")
        checks["openai"] = "error"
    
    # Check MCP server availability
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(config.MCP_SSE_URL, follow_redirects=True)
            checks["mcp_server"] = "available" if response.status_code < 500 else "unavailable"
    except Exception:
        checks["mcp_server"] = "unavailable"
    
    overall_status = "healthy" if all(
        v in ("healthy", "configured", "available") for v in checks.values()
    ) else "degraded"
    
    return {
        "status": overall_status,
        "checks": checks,
    }


@app.post("/launch")
@limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute")
async def launch(
    request: Request,
    p: Payload,
    api_key: str = Depends(verify_api_key),
):
    """Create a plan from the user's instruction, execute it,
    and return structured extraction results.
    
    Args:
        request: FastAPI request object (for rate limiting)
        p: Request payload with instruction and timeout
        api_key: Verified API key from header
    
    Returns:
        JSON payload: { goal, extracted, [error] }
    """
    request_id = getattr(request.state, "request_id", None)
    logger.info(f"Launch request received: {p.instruction[:100]}...", extra={"request_id": request_id, "api_key": api_key[:8]})
    
    try:
        # Generate a fresh plan.json for the given instruction
        try:
            generate_plan(p.instruction)
            logger.info("Plan generated successfully", extra={"request_id": request_id})
        except Exception as e:
            logger.error(f"Plan generation failed: {e}", extra={"request_id": request_id}, exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="Plan generation failed. Please check your instruction and try again.",
            )
        
        # Execute the robot runner that reads and executes plan.json
        returncode, stdout, stderr = _run_robot_runner(timeout_sec=p.timeout_sec, request_id=request_id)
        
        if returncode != 0:
            logger.error(f"Robot runner failed with return code {returncode}: {stderr}", extra={"request_id": request_id})
            raise HTTPException(
                status_code=500,
                detail="Execution failed. Please check your instruction and try again.",
            )
        
        # Check for a runner-signaled error line in the logs
        error_msg = _extract_error_line(stdout)
        
        # Prefer a well-formed JSON final_report printed by robotAI.py
        extracted = _parse_json_tail(stdout)
        
        # Fallback to collecting "key: value" lines from stdout
        if not extracted:
            extracted = _fallback_key_values(stdout)
        
        # Return structured result
        result = {
            "goal": p.instruction,
            "extracted": extracted,
        }
        
        if error_msg and not extracted:
            result["error"] = error_msg
            logger.warning(f"Execution completed with errors: {error_msg}", extra={"request_id": request_id})
        else:
            logger.info(f"Execution completed successfully. Extracted {len(extracted)} values", extra={"request_id": request_id})
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in launch endpoint: {e}", extra={"request_id": request_id}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again later.",
        )
