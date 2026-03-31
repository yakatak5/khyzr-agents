"""
Khyzr Agents API — Lambda proxy
Routes:
  POST /chat           → sync invoke (market-intelligence, ap, ar, raffle, inventory)
  POST /jobs           → async job start (terraform-hardening)
  GET  /jobs/{job_id}  → poll job status
"""
import boto3
import json
import os
import re
import uuid
import time
from decimal import Decimal

REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')
JOBS_TABLE = os.environ.get('JOBS_TABLE', 'khyzr-agent-jobs')
WORKER_FUNCTION = os.environ.get('WORKER_FUNCTION', 'khyzr-agents-worker')

def decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

AGENT_RUNTIMES = {
    'market-intelligence': os.environ.get('RUNTIME_MARKET_INTELLIGENCE', 'khyzr_market_intelligence_demo-9ilDrbFvhG'),
    'ap-automation':       os.environ.get('RUNTIME_AP_AUTOMATION',       'khyzr_ap_automation_demo-HR6p34ANEs'),
    'ar-collections':      os.environ.get('RUNTIME_AR_COLLECTIONS',      'khyzr_ar_collections_demo-FaFTsVGr0Z'),
    'raffle':              os.environ.get('RUNTIME_RAFFLE',               'khyzr_raffle_demo-8uf6GjHz29'),
    'inventory':           os.environ.get('RUNTIME_INVENTORY',           'khyzr_inventory_demo-XyJ14H6gv3'),
    'terraform-hardening': os.environ.get('RUNTIME_TERRAFORM',           'khyzr_terraform_hardening_demo-Ry8vUv31X6'),
}

ASYNC_AGENTS = {'terraform-hardening'}

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
    'Content-Type': 'application/json',
}

def extract_download_url(text):
    match = re.search(r'---\s*\nDOWNLOAD_URL:\s*(https?://\S+)\s*\n---', text)
    if match:
        url = match.group(1).strip()
        cleaned = (text[:match.start()] + '\n\n' + text[match.end():]).strip()
        return url, cleaned
    match = re.search(r'DOWNLOAD_URL:\s*(https?://\S+)', text)
    if match:
        url = match.group(1).strip()
        cleaned = (text[:match.start()] + text[match.end():]).strip()
        return url, cleaned
    return None, text

def invoke_agent(agent_id, message):
    """Invoke an AgentCore runtime and return the result dict."""
    runtime_id  = AGENT_RUNTIMES[agent_id]
    account_id  = boto3.client('sts').get_caller_identity()['Account']
    runtime_arn = f'arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{runtime_id}'

    if agent_id in ('raffle', 'inventory', 'terraform-hardening'):
        payload = json.loads(message) if message.strip().startswith('{') else {'prompt': message}
    else:
        payload = {'prompt': message}

    client = boto3.client('bedrock-agentcore', region_name=REGION)
    resp   = client.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=json.dumps(payload))
    result = json.loads(resp['response'].read())
    response_text = result.get('result') or result.get('output') or result.get('response') or str(result)

    out = {'response': response_text, 'agent_id': agent_id}
    if agent_id == 'terraform-hardening':
        download_url, response_text = extract_download_url(response_text)
        out['response'] = response_text
        if download_url:
            out['download_url'] = download_url
            out['download_filename'] = 'main-hardened.tf'
    return out

def lambda_handler(event, context):
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path   = event.get('rawPath', '/')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

    # ── GET /jobs/{job_id} ── poll status
    if method == 'GET' and path.startswith('/jobs/'):
        job_id = path.split('/')[-1]
        try:
            ddb  = boto3.resource('dynamodb', region_name=REGION)
            tbl  = ddb.Table(JOBS_TABLE)
            item = tbl.get_item(Key={'job_id': job_id}).get('Item')
            if not item:
                return {'statusCode': 404, 'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'Job not found'})}
            return {'statusCode': 200, 'headers': CORS_HEADERS,
                    'body': json.dumps(item, default=decimal_default)}
        except Exception as e:
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}

    # ── POST /jobs ── start async job
    if method == 'POST' and path == '/jobs':
        try:
            body       = json.loads(event.get('body', '{}'))
            agent_id   = body.get('agent_id', '')
            message    = body.get('message', '')
            job_id     = str(uuid.uuid4())

            if not agent_id or agent_id not in AGENT_RUNTIMES:
                return {'statusCode': 400, 'headers': CORS_HEADERS,
                        'body': json.dumps({'error': f"Unknown agent_id. Valid: {list(AGENT_RUNTIMES.keys())}"})}
            if not message:
                return {'statusCode': 400, 'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'message is required'})}

            # Write pending job to DynamoDB
            ddb = boto3.resource('dynamodb', region_name=REGION)
            tbl = ddb.Table(JOBS_TABLE)
            tbl.put_item(Item={
                'job_id':   job_id,
                'status':   'running',
                'agent_id': agent_id,
                'ttl':      int(time.time()) + 86400,  # 24h TTL
            })

            # Fire-and-forget worker Lambda
            lam = boto3.client('lambda', region_name=REGION)
            lam.invoke(
                FunctionName=WORKER_FUNCTION,
                InvocationType='Event',  # async — don't wait
                Payload=json.dumps({'job_id': job_id, 'agent_id': agent_id, 'message': message})
            )

            return {'statusCode': 202, 'headers': CORS_HEADERS,
                    'body': json.dumps({'job_id': job_id, 'status': 'running'})}
        except Exception as e:
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}

    # ── POST /chat ── sync invoke
    if method == 'POST' and path == '/chat':
        try:
            body       = json.loads(event.get('body', '{}'))
            agent_id   = body.get('agent_id', '')
            message    = body.get('message', '')
            session_id = body.get('session_id', str(uuid.uuid4()))

            if not agent_id or agent_id not in AGENT_RUNTIMES:
                return {'statusCode': 400, 'headers': CORS_HEADERS,
                        'body': json.dumps({'error': f"Unknown agent_id. Valid: {list(AGENT_RUNTIMES.keys())}"})}
            if not message:
                return {'statusCode': 400, 'headers': CORS_HEADERS,
                        'body': json.dumps({'error': 'message is required'})}

            result = invoke_agent(agent_id, message)
            result['session_id'] = session_id
            return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': json.dumps(result)}
        except Exception as e:
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}

    return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Not found'})}
