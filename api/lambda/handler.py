"""
handler.py — Khyzr Agents API Gateway + Lambda Proxy

Routes POST /chat requests to the correct AgentCore runtime based on agent_id.
No AWS credentials needed by the caller — the Lambda's IAM role handles auth.
"""

import json
import logging
import uuid
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Agent routing map ─────────────────────────────────────────────────────────
AGENT_RUNTIMES = {
    "market-intelligence": "khyzr_market_intelligence_demo-IXK91q23u1",
    "ap-automation":       "khyzr_ap_automation_demo-yXLiHZ39Ob",
    "ar-collections":      "khyzr_ar_collections_demo-HZchkDGBs5",
}

# ── CORS headers returned with every response ─────────────────────────────────
CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Content-Type":                 "application/json",
}

# ── Cold-start: resolve AWS account id once ───────────────────────────────────
try:
    _ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
    logger.info("Resolved account id: %s", _ACCOUNT_ID)
except Exception as exc:  # noqa: BLE001
    _ACCOUNT_ID = None
    logger.warning("Could not resolve account id at cold start: %s", exc)


def _runtime_arn(runtime_name: str) -> str:
    """Build the full ARN for an AgentCore runtime."""
    return f"arn:aws:bedrock-agentcore:us-east-1:{_ACCOUNT_ID}:runtime/{runtime_name}"


def _ok(body: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def lambda_handler(event, context):  # noqa: ARG001
    logger.info("Event: %s", json.dumps(event))

    # ── Handle CORS preflight ─────────────────────────────────────────────────
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _ok({}, 200)

    # ── Parse request body ────────────────────────────────────────────────────
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _err("Invalid JSON in request body")

    agent_id  = body.get("agent_id", "").strip()
    message   = body.get("message",  "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    # ── Validate inputs ───────────────────────────────────────────────────────
    if not agent_id:
        return _err("Missing required field: agent_id")
    if not message:
        return _err("Missing required field: message")
    if agent_id not in AGENT_RUNTIMES:
        valid = ", ".join(sorted(AGENT_RUNTIMES))
        return _err(f"Unknown agent_id '{agent_id}'. Valid values: {valid}")
    if not _ACCOUNT_ID:
        return _err("Lambda could not resolve AWS account id — check IAM role", 500)

    # ── Invoke AgentCore runtime ──────────────────────────────────────────────
    runtime_name = AGENT_RUNTIMES[agent_id]
    runtime_arn  = _runtime_arn(runtime_name)
    logger.info("Invoking runtime %s for agent %s (session %s)", runtime_arn, agent_id, session_id)

    try:
        client = boto3.client("bedrock-agentcore", region_name="us-east-1")
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            payload=json.dumps({"prompt": message}),
        )
        raw_body = resp["response"].read()
        result   = json.loads(raw_body)
        logger.info("AgentCore response keys: %s", list(result.keys()) if isinstance(result, dict) else type(result))

        # Extract the agent's text reply — handle common response shapes
        if isinstance(result, dict):
            agent_reply = (
                result.get("output")
                or result.get("response")
                or result.get("text")
                or result.get("content")
                or result.get("message")
                or json.dumps(result)
            )
        else:
            agent_reply = str(result)

    except client.exceptions.ResourceNotFoundException:
        return _err(f"AgentCore runtime '{runtime_name}' not found. Is it deployed?", 404)
    except client.exceptions.AccessDeniedException:
        return _err("Lambda IAM role lacks permission to invoke this runtime", 403)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentCore invocation failed")
        return _err(f"AgentCore error: {exc}", 502)

    return _ok({
        "response":   agent_reply,
        "agent_id":   agent_id,
        "session_id": session_id,
    })
