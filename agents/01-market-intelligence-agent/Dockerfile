"""
Market Intelligence Agent — Lambda Dockerfile
Packages the agent for AWS Lambda / AgentCore deployment.
"""

FROM public.ecr.aws/lambda/python:3.12

# Install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target ${LAMBDA_TASK_ROOT}

# Copy agent source
COPY src/ ${LAMBDA_TASK_ROOT}/

# Lambda handler entrypoint
CMD ["agent.handler"]
