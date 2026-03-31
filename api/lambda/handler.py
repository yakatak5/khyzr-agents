"""
Khyzr Agents API — Lambda proxy
Routes POST /chat requests to the correct AgentCore runtime.
"""
import boto3
import json
import os
import uuid

REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')

AGENT_RUNTIMES = {
    'market-intelligence': os.environ.get('RUNTIME_MARKET_INTELLIGENCE', 'khyzr_market_intelligence_demo-9ilDrbFvhG'),
    'ap-automation':       os.environ.get('RUNTIME_AP_AUTOMATION',       'khyzr_ap_automation_demo-HR6p34ANEs'),
    'ar-collections':      os.environ.get('RUNTIME_AR_COLLECTIONS',      'khyzr_ar_collections_demo-FaFTsVGr0Z'),
    'raffle':              os.environ.get('RUNTIME_RAFFLE',               'khyzr_raffle_demo-8uf6GjHz29'),
    'inventory':           os.environ.get('RUNTIME_INVENTORY',           'khyzr_inventory_demo-XyJ14H6gv3'),
}

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,OPTIONS',
    'Content-Type': 'application/json',
}

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

        runtime_id = AGENT_RUNTIMES[agent_id]
        account_id = boto3.client('sts').get_caller_identity()['Account']
        runtime_arn = f'arn:aws:bedrock-agentcore:{REGION}:{account_id}:runtime/{runtime_id}'

        # For raffle agent, pass bucket/key from message if provided
        if agent_id == 'raffle':
            payload = json.loads(message) if message.startswith('{') else {'prompt': message}
        else:
            payload = {'prompt': message}

        client = boto3.client('bedrock-agentcore', region_name=REGION)
        resp = client.invoke_agent_runtime(agentRuntimeArn=runtime_arn, payload=json.dumps(payload))
        result = json.loads(resp['response'].read())
        response_text = result.get('result') or result.get('output') or result.get('response') or str(result)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'response': response_text, 'agent_id': agent_id, 'session_id': session_id})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }
