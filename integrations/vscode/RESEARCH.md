# VSCode Extension Integration Research

Date: 2026-02-26
Researcher: AgentTalk automated research task

---

## Summary

This document covers the VSCode extension API approach for intercepting AI coding
agent responses (Roo Code, KiloCode, GitHub Copilot Chat) and sending them to
the AgentTalk TTS service.

---

## VSCode Extension API for AI Output Interception

### Available Interception Points

The VSCode extension API (as of early 2026) provides these relevant surfaces:

#### 1. vscode.chat (Chat Participant API)
- `vscode.chat.createChatParticipant()` — register as a chat participant
- Cannot intercept *other* extensions' responses via the chat API
- Useful for adding AgentTalk as a chat participant but NOT for listening to Roo/Kilo

#### 2. vscode.workspace.onDidChangeTextDocument
- Fires when any text document changes (including AI-written code)
- Captures code insertions but not conversational AI chat responses
- Unsuitable for chat output interception

#### 3. Output Channel Monitoring
- Extensions can create Output Channels but cannot read other extensions' output channels
- VSCode's sandboxed extension model prevents cross-extension output interception

#### 4. Inter-Extension Communication (ExtensionAPI)
- VSCode extensions can export APIs: `extension.exports`
- To intercept Roo Code responses, AgentTalk must use Roo Code's exported extension API

---

## Roo Code Extension API

**Repository:** https://github.com/RooCodeInc/Roo-Code

Roo Code (formerly Roo-Cline) is a VSCode extension. Based on the public repository:

### Available Extension Exports
Roo Code exports an API from its extension entrypoint. The key surface is:

```typescript
// Accessing Roo Code's exported API
const rooExtension = vscode.extensions.getExtension('rooveterinaryinc.roo-cline');
if (rooExtension) {
  const rooApi = await rooExtension.activate();
  // rooApi may expose events for messages
}
```

The exact event names depend on the Roo Code version. Known patterns:
- `onDidReceiveMessage` — fires when Roo receives or sends a message
- The API is not formally published/stabilized in 2026; subject to change

### Roo Code Message Events (best-effort)
Based on source code inspection:
- Roo Code uses a webview-based UI (similar to Cline)
- Message interception requires hooking into the webview message bus or extension API
- The extension exposes `onDidReceiveMessage` via its exported API

---

## KiloCode Extension API

**Repository:** https://github.com/kilo-org/kilocode

KiloCode is a fork/competitor to Roo Code with similar architecture.

### Available Extension Exports
```typescript
const kiloExtension = vscode.extensions.getExtension('kilocode.kilocode');
if (kiloExtension) {
  const kiloApi = await kiloExtension.activate();
  // Similar API surface to Roo Code
}
```

KiloCode's extension API mirrors Roo Code's due to shared heritage.

---

## GitHub Copilot Chat

Copilot Chat uses the official `vscode.chat` API. AgentTalk can register as a
middleware/listener by:
- Registering a chat response handler that wraps Copilot responses
- Using `vscode.chat.createChatParticipant()` with a pass-through handler

This is the most reliable approach for Copilot but does not intercept Roo/Kilo.

---

## Recommended Architecture

Given the limitations of direct API interception, the AgentTalk VSCode extension
uses a **multi-strategy** approach:

### Strategy 1: Roo Code / KiloCode Extension API
- Activate and access the exported API of known AI extensions
- Register a listener on their response events
- Forward response text to localhost:5050/speak

```typescript
async function hookRooCode(context: vscode.ExtensionContext) {
  const rooExt = vscode.extensions.getExtension('rooveterinaryinc.roo-cline');
  if (!rooExt) return;
  const api = await rooExt.activate();
  if (api?.onDidReceiveMessage) {
    api.onDidReceiveMessage((msg: any) => {
      if (msg.type === 'partialMessage' && msg.partialMessage?.role === 'assistant') {
        speakText(msg.partialMessage.content);
      }
    });
  }
}
```

### Strategy 2: Manual "Speak Last Response" Command
- Register a `agenttalk.speakLast` command in the command palette
- User triggers it after reading an AI response to hear it spoken
- Reads from clipboard or selection

### Strategy 3: Status Bar Integration
- Always-visible status bar item showing AgentTalk state (Speaking / Muted / Offline)
- Click to mute/unmute
- Shows port status (connected / disconnected)

---

## VSCode Marketplace Publish Requirements

### Prerequisites
1. Create a publisher account at https://marketplace.visualstudio.com/manage
2. Install `vsce` (Visual Studio Code Extension manager):
   ```bash
   npm install -g @vscode/vsce
   ```
3. Create a Personal Access Token (PAT) from Azure DevOps

### Build and Package
```bash
cd integrations/vscode
npm install
vsce package
# Produces: agenttalk-vscode-1.0.0.vsix
```

### Publish
```bash
vsce publish
# OR: vsce publish -p <PAT>
```

### package.json Requirements
- `publisher` field must match your marketplace publisher ID
- `engines.vscode` must specify minimum VSCode version
- `categories` should include "AI" and "Other"
- `activationEvents` must be specified

---

## Extension Structure

```
integrations/vscode/
├── package.json          — Extension manifest
├── src/
│   └── extension.ts      — Main extension entry point
├── tsconfig.json
├── .vscodeignore
└── README.md
```

---

## Decision: Implementation Target

Given research findings:

1. **Primary:** Roo Code and KiloCode extension API interception (best UX)
2. **Fallback:** Manual command `agenttalk.speakLast` for any AI extension
3. **Status bar:** Always-visible mute/unmute toggle

The extension will:
- Activate on VSCode startup (`"*"` activation event)
- Check AgentTalk health every 30 seconds
- Hook into Roo Code and KiloCode if installed
- Provide a command palette entry and status bar item

---

## References

- VSCode Extension API: https://code.visualstudio.com/api
- Roo Code GitHub: https://github.com/RooCodeInc/Roo-Code
- KiloCode GitHub: https://github.com/kilo-org/kilocode
- vsce documentation: https://code.visualstudio.com/api/working-with-extensions/publishing-extension
- VSCode chat API: https://code.visualstudio.com/api/extension-guides/chat
