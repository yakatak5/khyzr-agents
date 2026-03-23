FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/

# AgentCore requires /invocations (POST) and /ping (GET) endpoints
# BedrockAgentCoreApp.run() starts a uvicorn HTTP server on port 8080
EXPOSE 8080

# Health check — AgentCore polls /ping before marking READY
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping')" || exit 1

CMD ["python", "src/agent.py"]
