# AgentTalk Start

Ensure the AgentTalk TTS service is running before beginning any session.

## Steps

1. Check if AgentTalk is running:
   ```bash
   curl -s http://localhost:5050/health 2>/dev/null || echo "offline"
   ```

2. If the response is not `{"status": "ok"}`, start the service:
   - **Windows:** `start pythonw -m agenttalk.service`
   - **macOS/Linux:** `python -m agenttalk.service &`

3. Wait 3 seconds, then verify health again.

AgentTalk runs on http://localhost:5050. No data leaves your machine.
