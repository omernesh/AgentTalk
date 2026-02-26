# AgentTalk VSCode Extension

Real-time text-to-speech for AI coding agents in VSCode.
Speaks Roo Code and KiloCode responses aloud using a local offline TTS engine.

## Requirements

1. Install the AgentTalk service:
   ```bash
   pip install agenttalk
   agenttalk setup
   ```
2. Start the service: `python -m agenttalk.service`

## Features

- Automatically intercepts Roo Code and KiloCode responses
- Status bar item showing service state (Online / Muted / Offline)
- Click status bar to mute/unmute
- Command palette: `AgentTalk: Speak Selected Text`
- Auto-start service on VSCode launch (optional setting)

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `agenttalk.enabled` | `true` | Enable TTS integration |
| `agenttalk.port` | `5050` | AgentTalk service port |
| `agenttalk.autoStart` | `false` | Auto-start service when VSCode opens |
| `agenttalk.healthCheckInterval` | `30` | Health check interval in seconds |

## Publish

This extension is ready to publish to the VSCode Marketplace.
Ensure you have a publisher account at https://marketplace.visualstudio.com/manage
then update the `publisher` field in `package.json` and run:

```bash
vsce publish
```
