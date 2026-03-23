#!/usr/bin/env python3
"""
Khyzr Agents Demo UI — local web server
Proxies prompts to AgentCore runtimes using local AWS credentials.
Run: python3 server.py
"""
import json, os, sys, time, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── Agent registry ─────────────────────────────────────────────────────────
AGENTS = [
    {
        "id": "market-intelligence",
        "name": "Market Intelligence",
        "number": "01",
        "domain": "Executive Strategy",
        "description": "Monitors competitor news & SEC filings. Delivers executive briefings.",
        "arn": "arn:aws:bedrock-agentcore:us-east-1:110276528370:runtime/khyzr_market_intelligence_demo-IXK91q23u1",
        "placeholder": "Run a competitive briefing on OpenAI and Anthropic — search recent news and summarize key moves.",
        "color": "#6366f1",
    },
    {
        "id": "ap-automation",
        "name": "AP Automation",
        "number": "36",
        "domain": "Finance & Accounting",
        "description": "Processes invoices, matches POs, flags discrepancies, routes for approval.",
        "arn": "arn:aws:bedrock-agentcore:us-east-1:110276528370:runtime/khyzr_ap_automation_demo-yXLiHZ39Ob",
        "placeholder": "Process invoice INV-2024-08821 from Apex Supply Co — extract data, match PO-2024-00312, flag discrepancies, route for approval.",
        "color": "#10b981",
    },
    {
        "id": "ar-collections",
        "name": "AR Collections",
        "number": "40",
        "domain": "Finance & Accounting",
        "description": "Scores collection risk, drafts outreach emails, escalates overdue accounts.",
        "arn": "arn:aws:bedrock-agentcore:us-east-1:110276528370:runtime/khyzr_ar_collections_demo-HZchkDGBs5",
        "placeholder": "Fetch the aging AR report from s3://khyzr-ar-collections-demo-reports-110276528370/reports/aging-report-demo.json and give me a risk-tiered summary with recommended actions.",
        "color": "#f59e0b",
    },
]

def get_boto3_client():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pip-bin'))
        import boto3
        return boto3.client('bedrock-agentcore', region_name='us-east-1')
    except Exception as e:
        raise RuntimeError(f"Failed to create boto3 client: {e}")

def invoke_agent(arn, prompt):
    client = get_boto3_client()
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        payload=json.dumps({'prompt': prompt}).encode()
    )
    raw = resp['response'].read()
    try:
        return json.loads(raw).get('result', raw.decode())
    except:
        return raw.decode()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/agents':
            self.send_json(200, AGENTS)
        elif parsed.path == '/health':
            self.send_json(200, {'status': 'ok'})
        else:
            self.send_html(HTML)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/invoke':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            agent_id = body.get('agent_id')
            prompt = body.get('prompt', '').strip()

            agent = next((a for a in AGENTS if a['id'] == agent_id), None)
            if not agent:
                return self.send_json(404, {'error': f'Unknown agent: {agent_id}'})
            if not prompt:
                return self.send_json(400, {'error': 'Prompt is required'})

            try:
                t0 = time.time()
                result = invoke_agent(agent['arn'], prompt)
                elapsed = round(time.time() - t0, 1)
                self.send_json(200, {'result': result, 'elapsed': elapsed})
            except Exception as e:
                tb = traceback.format_exc()
                self.send_json(500, {'error': str(e), 'detail': tb[-500:]})
        else:
            self.send_json(404, {'error': 'Not found'})

# ── HTML (single-file SPA) ─────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Khyzr Agents</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2d3250;
    --text: #e2e8f0;
    --muted: #8892a4;
    --accent: #6366f1;
  }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; display: flex; flex-direction: column; }

  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 0 24px; height: 56px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }
  header span { font-size: 13px; color: var(--muted); }
  .badge { background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid rgba(99,102,241,0.3); border-radius: 20px; padding: 2px 10px; font-size: 11px; font-weight: 600; }

  .layout { display: flex; flex: 1; overflow: hidden; height: calc(100vh - 56px); }

  /* Sidebar */
  .sidebar { width: 280px; flex-shrink: 0; background: var(--surface); border-right: 1px solid var(--border); overflow-y: auto; padding: 16px 12px; display: flex; flex-direction: column; gap: 6px; }
  .sidebar-label { font-size: 10px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; padding: 8px 8px 4px; }
  .agent-btn { display: flex; align-items: flex-start; gap: 10px; padding: 10px 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; background: none; text-align: left; width: 100%; transition: all 0.15s; }
  .agent-btn:hover { background: var(--surface2); border-color: var(--border); }
  .agent-btn.active { background: var(--surface2); border-color: var(--border); }
  .agent-num { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: white; flex-shrink: 0; margin-top: 2px; }
  .agent-info { flex: 1; min-width: 0; }
  .agent-info strong { display: block; font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.3; }
  .agent-info small { font-size: 11px; color: var(--muted); display: block; margin-top: 2px; line-height: 1.4; }
  .agent-domain { font-size: 10px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 3px; }

  /* Chat area */
  .chat-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .chat-header { padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--surface); display: flex; align-items: center; gap: 12px; }
  .chat-header .agent-num { width: 38px; height: 38px; font-size: 13px; }
  .chat-header h2 { font-size: 16px; font-weight: 700; }
  .chat-header p { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .chat-header .status { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #10b981; }
  .status-dot.loading { background: #f59e0b; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  .messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  .msg { display: flex; gap: 10px; max-width: 860px; }
  .msg.user { flex-direction: row-reverse; align-self: flex-end; }
  .msg-avatar { width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; margin-top: 2px; }
  .msg.user .msg-avatar { background: var(--accent); color: white; }
  .msg-bubble { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; font-size: 14px; line-height: 1.65; max-width: 720px; }
  .msg.user .msg-bubble { background: rgba(99,102,241,0.12); border-color: rgba(99,102,241,0.3); }
  .msg-bubble pre { background: rgba(0,0,0,0.3); border-radius: 6px; padding: 10px 14px; font-size: 12px; overflow-x: auto; margin: 8px 0; white-space: pre-wrap; word-break: break-word; }
  .msg-meta { font-size: 11px; color: var(--muted); margin-top: 6px; }
  .msg-bubble p { margin: 6px 0; }
  .msg-bubble p:first-child { margin-top: 0; }
  .msg-bubble p:last-child { margin-bottom: 0; }
  .msg-bubble ul, .msg-bubble ol { padding-left: 20px; margin: 6px 0; }
  .msg-bubble li { margin: 3px 0; }
  .msg-bubble h1,.msg-bubble h2,.msg-bubble h3 { margin: 12px 0 6px; font-size: 15px; }
  .msg-bubble strong { color: #c7d2fe; }

  .typing { display: flex; align-items: center; gap: 6px; padding: 10px 14px; }
  .typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: bounce 1.2s infinite; }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }

  .input-area { padding: 16px 24px; border-top: 1px solid var(--border); background: var(--surface); }
  .input-row { display: flex; gap: 10px; align-items: flex-end; }
  textarea { flex: 1; background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; color: var(--text); font-size: 14px; font-family: inherit; resize: none; outline: none; min-height: 44px; max-height: 200px; line-height: 1.5; transition: border-color 0.15s; }
  textarea:focus { border-color: var(--accent); }
  textarea::placeholder { color: var(--muted); }
  button.send { background: var(--accent); border: none; border-radius: 10px; width: 44px; height: 44px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: opacity 0.15s; }
  button.send:hover { opacity: 0.85; }
  button.send:disabled { opacity: 0.4; cursor: not-allowed; }
  button.send svg { width: 18px; height: 18px; fill: white; }
  .input-hint { font-size: 11px; color: var(--muted); margin-top: 8px; }

  .welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; text-align: center; padding: 40px; gap: 12px; }
  .welcome h2 { font-size: 22px; font-weight: 700; }
  .welcome p { color: var(--muted); font-size: 14px; max-width: 400px; line-height: 1.6; }

  .error-bubble { background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3); color: #fca5a5; }

  ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<header>
  <span style="font-size:22px">🤖</span>
  <h1>Khyzr Agents</h1>
  <span class="badge">AgentCore • Live</span>
</header>

<div class="layout">
  <aside class="sidebar" id="sidebar"></aside>
  <div class="chat-area" id="chat-area">
    <div class="welcome" id="welcome">
      <div style="font-size:48px">🤖</div>
      <h2>Select an Agent</h2>
      <p>Choose an agent from the sidebar to start a conversation. Each agent is deployed live on Amazon Bedrock AgentCore.</p>
    </div>
  </div>
</div>

<script>
const agents = [];
let activeAgent = null;
const histories = {};

async function loadAgents() {
  const res = await fetch('/api/agents');
  const data = await res.json();
  agents.push(...data);
  renderSidebar();
  // auto-select first
  if (agents.length) selectAgent(agents[0].id);
}

function renderSidebar() {
  const el = document.getElementById('sidebar');
  const groups = {};
  agents.forEach(a => { (groups[a.domain] = groups[a.domain] || []).push(a); });
  let html = '';
  for (const [domain, list] of Object.entries(groups)) {
    html += `<div class="sidebar-label">${domain}</div>`;
    list.forEach(a => {
      html += `<button class="agent-btn" id="btn-${a.id}" onclick="selectAgent('${a.id}')">
        <div class="agent-num" style="background:${a.color}">${a.number}</div>
        <div class="agent-info">
          <strong>${a.name}</strong>
          <small>${a.description}</small>
        </div>
      </button>`;
    });
  }
  el.innerHTML = html;
}

function selectAgent(id) {
  activeAgent = agents.find(a => a.id === id);
  if (!activeAgent) return;
  if (!histories[id]) histories[id] = [];
  document.querySelectorAll('.agent-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + id)?.classList.add('active');
  renderChat();
}

function renderChat() {
  const a = activeAgent;
  const msgs = histories[a.id] || [];
  document.getElementById('chat-area').innerHTML = `
    <div class="chat-header">
      <div class="agent-num" style="background:${a.color}">${a.number}</div>
      <div>
        <h2>${a.name}</h2>
        <p>${a.description}</p>
      </div>
      <div class="status">
        <div class="status-dot" id="status-dot"></div>
        <span id="status-text">Ready</span>
      </div>
    </div>
    <div class="messages" id="messages">${msgs.length ? msgs.map(renderMsg).join('') : renderEmptyState(a)}</div>
    <div class="input-area">
      <div class="input-row">
        <textarea id="prompt-input" placeholder="${a.placeholder}" rows="1" onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
        <button class="send" id="send-btn" onclick="sendMessage()">
          <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
      <div class="input-hint">Press Enter to send · Shift+Enter for new line</div>
    </div>`;
  scrollBottom();
}

function renderEmptyState(a) {
  return `<div class="welcome" style="flex:1">
    <div class="agent-num" style="background:${a.color};width:56px;height:56px;font-size:18px;border-radius:12px">${a.number}</div>
    <h2>${a.name} Agent</h2>
    <p>${a.description}</p>
    <p style="margin-top:8px;font-size:13px;color:#6b7280">Try: <em style="color:#818cf8">"${a.placeholder.substring(0,80)}..."</em></p>
  </div>`;
}

function renderMsg(m) {
  const isUser = m.role === 'user';
  const avatar = isUser ? 'Y' : activeAgent.number;
  const avatarBg = isUser ? '' : `style="background:${activeAgent.color}"`;
  const content = isUser ? escapeHtml(m.content) : formatMarkdown(m.content);
  const meta = m.elapsed ? `<div class="msg-meta">${m.elapsed}s</div>` : '';
  const errorClass = m.error ? ' error-bubble' : '';
  return `<div class="msg ${isUser ? 'user' : 'agent'}">
    <div class="msg-avatar" ${avatarBg}>${avatar}</div>
    <div><div class="msg-bubble${errorClass}">${content}</div>${meta}</div>
  </div>`;
}

function formatMarkdown(text) {
  let h = escapeHtml(text);
  // headers
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // bold/italic
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // code blocks
  h = h.replace(/```[\s\S]*?```/g, m => `<pre>${m.slice(3,-3).trim()}</pre>`);
  h = h.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.3);padding:1px 5px;border-radius:3px;font-size:12px">$1</code>');
  // bullets
  h = h.replace(/^[-•] (.+)$/gm, '<li>$1</li>');
  h = h.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
  h = h.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  // emoji-prefixed lines as bullets
  h = h.replace(/^([🚨✅❌⚠️🔴🟡🟢📊💰🔍]) (.+)$/gm, '<li>$1 $2</li>');
  // paragraphs
  h = h.split('\n\n').map(p => p.trim() ? `<p>${p.replace(/\n/g,'<br>')}</p>` : '').join('');
  return h || escapeHtml(text);
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

async function sendMessage() {
  const input = document.getElementById('prompt-input');
  const prompt = input?.value.trim();
  if (!prompt || !activeAgent) return;

  const id = activeAgent.id;
  histories[id].push({ role: 'user', content: prompt });
  input.value = '';
  input.style.height = 'auto';

  // Show typing
  renderMessages(id);
  appendTyping();
  setLoading(true);

  try {
    const res = await fetch('/api/invoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: id, prompt }),
    });
    const data = await res.json();
    if (data.error) {
      histories[id].push({ role: 'agent', content: `Error: ${data.error}`, error: true });
    } else {
      histories[id].push({ role: 'agent', content: data.result, elapsed: data.elapsed });
    }
  } catch (e) {
    histories[id].push({ role: 'agent', content: `Network error: ${e.message}`, error: true });
  }

  setLoading(false);
  renderMessages(id);
  scrollBottom();
}

function renderMessages(id) {
  const msgs = document.getElementById('messages');
  if (!msgs) return;
  const a = activeAgent;
  if (!a || a.id !== id) return;
  const history = histories[id] || [];
  msgs.innerHTML = history.length ? history.map(renderMsg).join('') : renderEmptyState(a);
}

function appendTyping() {
  const msgs = document.getElementById('messages');
  if (!msgs) return;
  // remove empty state if present
  const welcome = msgs.querySelector('.welcome');
  if (welcome) welcome.remove();
  const t = document.createElement('div');
  t.className = 'msg agent';
  t.id = 'typing-indicator';
  t.innerHTML = `<div class="msg-avatar" style="background:${activeAgent.color}">${activeAgent.number}</div>
    <div class="msg-bubble"><div class="typing"><span></span><span></span><span></span></div></div>`;
  msgs.appendChild(t);
  scrollBottom();
}

function setLoading(on) {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const btn = document.getElementById('send-btn');
  if (dot) dot.className = 'status-dot' + (on ? ' loading' : '');
  if (txt) txt.textContent = on ? 'Thinking...' : 'Ready';
  if (btn) btn.disabled = on;
}

function scrollBottom() {
  const msgs = document.getElementById('messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

loadAgents();
</script>
</body>
</html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"🤖 Khyzr Agents Demo UI")
    print(f"   http://localhost:{port}")
    print(f"   Agents: {len(AGENTS)} deployed on AgentCore")
    print(f"   Press Ctrl+C to stop\n")
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
