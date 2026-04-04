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
        JSON string with winner(s) details including full name from first+last columns
    """
    try:
        data = json.loads(entries_json)
        entries = data.get("entries", [])

        if not entries:
            return json.dumps({"error": "No entries to pick from"})

        if num_winners > len(entries):
            num_winners = len(entries)

        winners = random.sample(entries, num_winners)

        def get_display_name(w):
            keys = [k.lower() for k in w.keys()]
            orig_keys = list(w.keys())

            # Try to find first name + last name columns and combine them
            first_key = next((orig_keys[i] for i, k in enumerate(keys)
                              if k in ("first name", "firstname", "first_name", "given name", "given_name")), None)
            last_key  = next((orig_keys[i] for i, k in enumerate(keys)
                              if k in ("last name", "lastname", "last_name", "surname", "family name", "family_name")), None)

            if first_key and last_key:
                return f"{w.get(first_key, '').strip()} {w.get(last_key, '').strip()}".strip()

            # Single full-name column
            if name_field and name_field in w:
                return w[name_field]
            for candidate in ["name", "Name", "NAME", "full_name", "Full Name",
                               "Full_Name", "participant", "Participant"]:
                if candidate in w:
                    return w[candidate]

            # Fallback: first column
            return str(list(w.values())[0])

        winner_names = [get_display_name(w) for w in winners]

        result = {
            "total_entries": len(entries),
            "num_winners": len(winners),
            "winners": winners,
            "winner_names": winner_names,
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
1. Call load_entries_from_s3 to load the entries
2. Tell the user how many entries were loaded
3. Call pick_winners to randomly select the winner(s) — the tool will automatically detect First Name + Last Name columns and combine them
4. Announce each winner by their FULL NAME from the winner_names field in the tool result
5. Also show any other details from their row (email, phone, ticket number, etc.)

Format your announcement like:
🎉 **AND THE WINNER IS...**
# [Full Name]
[Other details from their row]

If multiple winners, number them: 🥇 1st Place, 🥈 2nd Place, etc.

Always use the winner_names from the pick_winners result — never make up or shorten names.
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
