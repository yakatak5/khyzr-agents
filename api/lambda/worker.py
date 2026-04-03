"""
Khyzr Agents Worker Lambda
Invoked async by the main handler for ALL agents.
Runs the AgentCore call, writes result back to DynamoDB.
"""
import boto3
import json
import os
import re
import time

REGION     = os.environ.get('AWS_REGION_NAME', 'us-east-1')
JOBS_TABLE = os.environ.get('JOBS_TABLE', 'khyzr-agent-jobs')

AGENT_RUNTIMES = {
    'market-intelligence': os.environ.get('RUNTIME_MARKET_INTELLIGENCE', 'khyzr_market_intelligence_demo-9ilDrbFvhG'),
    'ap-automation':       os.environ.get('RUNTIME_AP_AUTOMATION',       'khyzr_ap_automation_demo-HR6p34ANEs'),
    'ar-collections':      os.environ.get('RUNTIME_AR_COLLECTIONS',      'khyzr_ar_collections_demo-FaFTsVGr0Z'),
    'raffle':              os.environ.get('RUNTIME_RAFFLE',               'khyzr_raffle_demo-8uf6GjHz29'),
    'inventory':           os.environ.get('RUNTIME_INVENTORY',           'khyzr_inventory_demo-XyJ14H6gv3'),
    'terraform-hardening': os.environ.get('RUNTIME_TERRAFORM',           'khyzr_terraform_hardening_demo-Ry8vUv31X6'),
    'threat-modeling':     os.environ.get('RUNTIME_THREAT_MODEL',        'khyzr_threat_model_demo-dASoTjBH8K'),
}

# Agents that pass message as raw JSON payload (file-based agents)
JSON_PAYLOAD_AGENTS = {
    'ap-automation', 'ar-collections', 'raffle',
    'inventory', 'terraform-hardening', 'threat-modeling'
}

# Agents that produce a downloadable file
DOWNLOAD_AGENTS = {
    'terraform-hardening': 'main-hardened.tf',
    'threat-modeling':     'threat-model-report.md',
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

def lambda_handler(event, context):
    job_id   = event['job_id']
    agent_id = event['agent_id']
    message  = event['message']

    ddb = boto3.resource('dynamodb', region_name=REGION)
    tbl = ddb.Table(JOBS_TABLE)

    try:
        runtime_id  = AGENT_RUNTIMES[agent_id]
        account_id  = boto3.client('sts').get_caller_identity()['Account']
        runtime_arn = f'arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{runtime_id}'

        # Build payload
        if agent_id in JSON_PAYLOAD_AGENTS and message.strip().startswith('{'):
            payload = json.loads(message)
        else:
            payload = {'prompt': message}

        client = boto3.client('bedrock-agentcore', region_name=REGION)
        resp   = client.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=json.dumps(payload))
        result = json.loads(resp['response'].read())
        response_text = result.get('result') or result.get('output') or result.get('response') or str(result)

        item = {
            'job_id':   job_id,
            'status':   'done',
            'agent_id': agent_id,
            'response': response_text,
            'ttl':      int(time.time()) + 86400,
        }

        # Extract download URL for agents that produce files
        if agent_id in DOWNLOAD_AGENTS:
            download_url, response_text = extract_download_url(response_text)
            item['response'] = response_text
            if download_url:
                item['download_url']      = download_url
                item['download_filename'] = DOWNLOAD_AGENTS[agent_id]

        tbl.put_item(Item=item)

    except Exception as e:
        tbl.put_item(Item={
            'job_id':  job_id,
            'status':  'error',
            'error':   str(e),
            'ttl':     int(time.time()) + 86400,
        })
