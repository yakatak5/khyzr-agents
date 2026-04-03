"""
Khyzr Agents API — Lambda proxy
All agents are async via POST /jobs + GET /jobs/{job_id}.
POST /chat is kept for backward compatibility — it starts a job and returns job_id.

Routes:
  POST /chat           → starts async job, returns { job_id, status: "running" }
  POST /jobs           → starts async job, returns { job_id, status: "running" }
  GET  /jobs/{job_id}  → poll job status/result
"""
import boto3
import json
import os
import uuid
import time
from decimal import Decimal

REGION          = os.environ.get('AWS_REGION_NAME', 'us-east-1')
JOBS_TABLE      = os.environ.get('JOBS_TABLE', 'khyzr-agent-jobs')
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
    'threat-modeling':     os.environ.get('RUNTIME_THREAT_MODEL',        'khyzr_threat_model_demo-dASoTjBH8K'),
}

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
    'Content-Type': 'application/json',
}

def start_job(agent_id, message):
    """Write a pending job to DynamoDB and fire the worker Lambda async."""
    job_id = str(uuid.uuid4())

    ddb = boto3.resource('dynamodb', region_name=REGION)
    tbl = ddb.Table(JOBS_TABLE)
    tbl.put_item(Item={
        'job_id':   job_id,
        'status':   'running',
        'agent_id': agent_id,
        'ttl':      int(time.time()) + 86400,
    })

    lam = boto3.client('lambda', region_name=REGION)
    lam.invoke(
        FunctionName=WORKER_FUNCTION,
        InvocationType='Event',  # fire-and-forget
        Payload=json.dumps({'job_id': job_id, 'agent_id': agent_id, 'message': message})
    )

    return job_id

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

    # ── POST /jobs or POST /chat ── start async job
    if method == 'POST' and path in ('/jobs', '/chat'):
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

            job_id = start_job(agent_id, message)

            return {'statusCode': 202, 'headers': CORS_HEADERS,
                    'body': json.dumps({'job_id': job_id, 'status': 'running', 'session_id': session_id})}

        except Exception as e:
            return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': str(e)})}

    return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Not found'})}
