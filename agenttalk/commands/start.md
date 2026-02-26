---
name: start
description: Start the AgentTalk TTS service if it is not already running
disable-model-invocation: true
allowed-tools: Bash
---

Start the AgentTalk TTS service.

First, check if it is already running:
```bash
curl -s http://localhost:5050/health --max-time 2
```

If the health check returns `"status": "ok"`, say "AgentTalk is already running."

If the health check fails (connection refused or timeout), launch the service:
```bash
python -c "
import subprocess, os
from pathlib import Path
appdata = Path(os.environ['APPDATA']) / 'AgentTalk'
pythonw = (appdata / 'pythonw_path.txt').read_text().strip()
service = (appdata / 'service_path.txt').read_text().strip()
subprocess.Popen(
    [pythonw, service],
    creationflags=0x00000008 | 0x00000200,
    close_fds=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print('Service launched')
"
```

If the launch command prints "Service launched", say "AgentTalk service is starting. It will be ready in about 10 seconds."
If the launch command raises FileNotFoundError (pythonw_path.txt or service_path.txt missing), say "AgentTalk is not set up yet. Run 'agenttalk setup' to complete installation."
