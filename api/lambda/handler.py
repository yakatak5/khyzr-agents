"""
Khyzr Agents API — Lambda proxy
Routes POST /chat requests to the correct AgentCore runtime.
"""
import boto3
import json
import os
import re
import uuid

REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')

AGENT_RUNTIMES = {
    'market-intelligence': os.environ.get('RUNTIME_MARKET_INTELLIGENCE', 'khyzr_market_intelligence_demo-9ilDrbFvhG'),
    'ap-automation':       os.environ.get('RUNTIME_AP_AUTOMATION',       'khyzr_ap_automation_demo-HR6p34ANEs'),
    'ar-collections':      os.environ.get('RUNTIME_AR_COLLECTIONS',      'khyzr_ar_collections_demo-FaFTsVGr0Z'),
    'raffle':              os.environ.get('RUNTIME_RAFFLE',               'khyzr_raffle_demo-8uf6GjHz29'),
    'inventory':           os.environ.get('RUNTIME_INVENTORY',           'khyzr_inventory_demo-XyJ14H6gv3'),
    'terraform-hardening': os.environ.get('RUNTIME_TERRAFORM',           'khyzr_terraform_hardening_demo-Ry8vUv31X6'),
}

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,OPTIONS',
    'Content-Type': 'application/json',
}

def extract_download_url(text):
    """Extract DOWNLOAD_URL marker from agent response, return (url, cleaned_text)."""
    match = re.search(r'---\s*\nDOWNLOAD_URL:\s*(https?://\S+)\s*\n---', text)
    if match:
        url = match.group(1).strip()
        cleaned = text[:match.start()].strip() + '\n\n' + text[match.end():].strip()
        return url, cleaned.strip()
    # Also try without dashes
    match = re.search(r'DOWNLOAD_URL:\s*(https?://\S+)', text)
    if match:
        url = match.group(1).strip()
        cleaned = text[:match.start()].strip() + text[match.end():].strip()
        return url, cleaned.strip()
    return None, text

def lambda_handler(event, context):
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

    try:
        body = json.loads(event.get('body', '{}'))
        agent_id   = body.get('agent_id', '')
        message    = body.get('message', '')
        session_id = body.get('session_id', str(uuid.uuid4()))

        if not agent_id or agent_id not in AGENT_RUNTIMES:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': f"Unknown agent_id. Valid: {list(AGENT_RUNTIMES.keys())}"})
            }

        if not message:
            return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'message is required'})}

        runtime_id  = AGENT_RUNTIMES[agent_id]
        account_id  = boto3.client('sts').get_caller_identity()['Account']
        runtime_arn = f'arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{runtime_id}'

        # Agents that accept JSON payloads directly
        if agent_id in ('raffle', 'inventory', 'terraform-hardening'):
            payload = json.loads(message) if message.strip().startswith('{') else {'prompt': message}
        else:
            payload = {'prompt': message}

        client = boto3.client('bedrock-agentcore', region_name=REGION)
        resp   = client.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=json.dumps(payload))
        result = json.loads(resp['response'].read())
        response_text = result.get('result') or result.get('output') or result.get('response') or str(result)

        # For terraform agent: parse out download URL, return separately
        download_url = None
        if agent_id == 'terraform-hardening':
            download_url, response_text = extract_download_url(response_text)

        resp_body = {
            'response':   response_text,
            'agent_id':   agent_id,
            'session_id': session_id,
        }
        if download_url:
            resp_body['download_url'] = download_url
            resp_body['download_filename'] = 'main-hardened.tf'

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(resp_body)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }
