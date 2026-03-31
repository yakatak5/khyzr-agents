"""
Raffle Agent
============
Takes an Excel sheet of names/entries, randomly selects a winner (or multiple winners).
Simple, fun, no DynamoDB or S3 required — just reads the file and picks.

Built with AWS Strands Agents + Amazon Bedrock AgentCore Runtime.
"""

import json
import os
import io
import random
import logging
import boto3
import openpyxl

from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("raffle-agent")

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def load_entries_from_s3(bucket: str, key: str) -> str:
    """
    Load raffle entries from an Excel file stored in S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key (e.g. 'raffle/entries.xlsx')

    Returns:
        JSON string with list of entries and column headers
    """
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"))
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()

        wb = openpyxl.load_workbook(io.BytesIO(data))
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return json.dumps({"error": "Excel file is empty"})

        headers = [str(h) if h is not None else f"Column{i+1}" for i, h in enumerate(rows[0])]
        entries = []
        for row in rows[1:]:
            if any(cell is not None for cell in row):
                entry = {headers[i]: (str(row[i]) if row[i] is not None else "") for i in range(len(headers))}
                entries.append(entry)

        logger.info(f"Loaded {len(entries)} entries from s3://{bucket}/{key}")
        return json.dumps({"headers": headers, "entries": entries, "total": len(entries)})
    except Exception as e:
        logger.error(f"Failed to load entries: {e}")
        return json.dumps({"error": str(e)})


@tool
def pick_winners(entries_json: str, num_winners: int = 1, name_field: str = "") -> str:
    """
    Randomly select winner(s) from a list of entries.

    Args:
        entries_json: JSON string of entries (from load_entries_from_s3)
        num_winners: Number of winners to select (default 1)
        name_field: Column name to use as the display name (auto-detected if empty)

    Returns:
        JSON string with winner(s) details
    """
    try:
        data = json.loads(entries_json)
        entries = data.get("entries", [])

        if not entries:
            return json.dumps({"error": "No entries to pick from"})

        if num_winners > len(entries):
            num_winners = len(entries)

        winners = random.sample(entries, num_winners)

        # Auto-detect name field if not provided
        if not name_field and winners:
            for candidate in ["name", "Name", "NAME", "full_name", "Full Name", "participant", "Participant"]:
                if candidate in winners[0]:
                    name_field = candidate
                    break
            if not name_field:
                name_field = list(winners[0].keys())[0]

        result = {
            "total_entries": len(entries),
            "num_winners": len(winners),
            "winners": winners,
            "winner_names": [w.get(name_field, str(w)) for w in winners],
        }
        logger.info(f"Selected {len(winners)} winner(s) from {len(entries)} entries")
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

_agent = None

def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        model = BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
        )
        _agent = Agent(
            model=model,
            tools=[load_entries_from_s3, pick_winners],
            system_prompt="""You are the Raffle Agent — a friendly, enthusiastic assistant for running fair random draws.

When given an S3 bucket and key for an Excel file:
1. Load the entries using load_entries_from_s3
2. Tell the user how many entries were found
3. Use pick_winners to randomly select the winner(s)
4. Announce the winner(s) in an exciting, celebratory way 🎉
5. Show all their details from the spreadsheet

If the user specifies how many winners they want, pick that many.
If no number is specified, pick 1 winner.

Keep it fun and energetic — this is a celebration!
""",
        )
    return _agent


# ---------------------------------------------------------------------------
# AgentCore entrypoint
# ---------------------------------------------------------------------------

@app.entrypoint
def invoke(payload):
    """
    Expected payload:
    {
        "prompt": "Pick a winner",           # optional custom prompt
        "bucket": "my-raffle-bucket",        # S3 bucket with the Excel file
        "key": "entries.xlsx",               # S3 key
        "num_winners": 1                     # optional, default 1
    }
    """
    bucket = payload.get("bucket", os.environ.get("RAFFLE_BUCKET", ""))
    key = payload.get("key", os.environ.get("RAFFLE_KEY", "entries.xlsx"))
    num_winners = payload.get("num_winners", 1)
    prompt = payload.get("prompt", "")

    if not prompt:
        if not bucket:
            return {"error": "Provide 'bucket' in payload or set RAFFLE_BUCKET env var"}
        prompt = f"Load the raffle entries from s3://{bucket}/{key} and pick {num_winners} winner(s). Announce them!"

    try:
        result = _get_agent()(prompt)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"Raffle agent error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    app.run()
