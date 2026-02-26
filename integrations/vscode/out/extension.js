"use strict";
/**
 * AgentTalk VSCode Extension
 *
 * Speaks AI coding agent responses aloud using the AgentTalk TTS service
 * (localhost:5050). Works with Roo Code, KiloCode, and GitHub Copilot Chat.
 *
 * Architecture:
 * - Zero TTS logic in this extension — all audio goes through localhost:5050
 * - Thin adapter: intercept text, POST to /speak, nothing else
 * - Status bar item shows service state (Speaking / Muted / Offline)
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const http = __importStar(require("http"));
const child_process = __importStar(require("child_process"));
const os = __importStar(require("os"));
// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const STATUS_ITEM_PRIORITY = 100;
// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let statusBarItem;
let healthCheckTimer;
let isServiceOnline = false;
let isMuted = false;
// ---------------------------------------------------------------------------
// HTTP helpers (zero dependencies — avoids bundler complexity)
// ---------------------------------------------------------------------------
function getPort() {
    return vscode.workspace
        .getConfiguration("agenttalk")
        .get("port", 5050);
}
/**
 * POST text to AgentTalk /speak endpoint.
 * Fire-and-forget — never throws, never blocks UI.
 */
function speakText(text) {
    if (!text || !text.trim()) {
        return;
    }
    const enabled = vscode.workspace
        .getConfiguration("agenttalk")
        .get("enabled", true);
    if (!enabled || isMuted) {
        return;
    }
    const port = getPort();
    const body = JSON.stringify({ text: text.trim() });
    const options = {
        hostname: "127.0.0.1",
        port,
        path: "/speak",
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
        },
    };
    const req = http.request(options, (res) => {
        res.resume(); // Drain response body to free socket
    });
    req.on("error", () => {
        // Service offline or busy — silent fail (status bar shows state)
        isServiceOnline = false;
        updateStatusBar();
    });
    req.write(body);
    req.end();
}
/**
 * GET /health to check if the service is alive.
 * Returns a Promise<boolean>.
 */
function checkHealth() {
    return new Promise((resolve) => {
        const port = getPort();
        const options = {
            hostname: "127.0.0.1",
            port,
            path: "/health",
            method: "GET",
        };
        const req = http.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => (data += chunk));
            res.on("end", () => {
                try {
                    const json = JSON.parse(data);
                    resolve(json.status === "ok");
                }
                catch {
                    resolve(false);
                }
            });
        });
        req.on("error", () => resolve(false));
        req.setTimeout(3000, () => {
            req.destroy();
            resolve(false);
        });
        req.end();
    });
}
/**
 * POST to /config to update a setting on the running service.
 */
function postConfig(config) {
    const port = getPort();
    const body = JSON.stringify(config);
    const options = {
        hostname: "127.0.0.1",
        port,
        path: "/config",
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(body),
        },
    };
    const req = http.request(options, (res) => {
        res.resume();
    });
    req.on("error", () => { }); // Best-effort
    req.write(body);
    req.end();
}
/**
 * POST to /stop to stop the running service.
 */
function postStop() {
    const port = getPort();
    const options = {
        hostname: "127.0.0.1",
        port,
        path: "/stop",
        method: "POST",
        headers: { "Content-Length": "0" },
    };
    const req = http.request(options, (res) => {
        res.resume();
        isServiceOnline = false;
        updateStatusBar();
        vscode.window.showInformationMessage("AgentTalk: Service stopped.");
    });
    req.on("error", () => {
        vscode.window.showWarningMessage("AgentTalk: Could not contact service (already stopped?).");
    });
    req.end();
}
// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------
function updateStatusBar() {
    if (!isServiceOnline) {
        statusBarItem.text = "$(mute) AgentTalk: Offline";
        statusBarItem.tooltip = "AgentTalk service is not running. Click to start.";
        statusBarItem.command = "agenttalk.startService";
        statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    }
    else if (isMuted) {
        statusBarItem.text = "$(mute) AgentTalk: Muted";
        statusBarItem.tooltip = "AgentTalk is muted. Click to unmute.";
        statusBarItem.command = "agenttalk.toggleMute";
        statusBarItem.backgroundColor = undefined;
    }
    else {
        statusBarItem.text = "$(unmute) AgentTalk";
        statusBarItem.tooltip = "AgentTalk is active. Click to mute.";
        statusBarItem.command = "agenttalk.toggleMute";
        statusBarItem.backgroundColor = undefined;
    }
}
// ---------------------------------------------------------------------------
// Health check loop
// ---------------------------------------------------------------------------
async function runHealthCheck() {
    const online = await checkHealth();
    if (online !== isServiceOnline) {
        isServiceOnline = online;
        updateStatusBar();
    }
}
function startHealthCheckLoop(intervalSeconds) {
    if (healthCheckTimer) {
        clearInterval(healthCheckTimer);
    }
    healthCheckTimer = setInterval(() => runHealthCheck(), intervalSeconds * 1000);
    // Run immediately on startup
    runHealthCheck();
}
// ---------------------------------------------------------------------------
// AI extension hooking — Roo Code / KiloCode
// ---------------------------------------------------------------------------
/**
 * Known AI coding extension IDs to hook into.
 * Multiple IDs per "product" to handle fork variations.
 */
const AI_EXTENSION_IDS = [
    "rooveterinaryinc.roo-cline", // Roo Code
    "RooVeterinaryInc.roo-cline",
    "kilo.kilocode", // KiloCode
    "kilocode.kilocode",
];
/**
 * Try to hook into an AI extension's exported API to intercept responses.
 * This is best-effort — the API shape varies per extension version.
 */
async function hookAiExtension(extensionId) {
    const ext = vscode.extensions.getExtension(extensionId);
    if (!ext) {
        return false;
    }
    try {
        const api = await ext.activate();
        if (!api) {
            return false;
        }
        // Pattern 1: onDidReceiveMessage (Roo Code / KiloCode pattern)
        if (typeof api.onDidReceiveMessage === "function") {
            api.onDidReceiveMessage((msg) => {
                if (!msg) {
                    return;
                }
                // Roo Code sends partialMessage events with assistant content
                if (msg.type === "partialMessage" &&
                    msg.partialMessage?.role === "assistant") {
                    const content = msg.partialMessage?.content;
                    if (typeof content === "string" && content.trim()) {
                        speakText(content);
                    }
                }
                // Some versions send a 'say' type directly
                if (msg.type === "say" && msg.say === "text" && msg.text) {
                    speakText(msg.text);
                }
            });
            return true;
        }
        // Pattern 2: onResponse (alternative API shape)
        if (typeof api.onResponse === "function") {
            api.onResponse((response) => {
                if (typeof response === "string") {
                    speakText(response);
                }
                else if (response?.text) {
                    speakText(response.text);
                }
            });
            return true;
        }
        return false;
    }
    catch {
        return false;
    }
}
async function hookAllAiExtensions() {
    let hookedCount = 0;
    for (const id of AI_EXTENSION_IDS) {
        const success = await hookAiExtension(id);
        if (success) {
            hookedCount++;
        }
    }
    if (hookedCount > 0) {
        vscode.window.setStatusBarMessage(`AgentTalk: hooked into ${hookedCount} AI extension(s)`, 5000);
    }
}
// ---------------------------------------------------------------------------
// Service start (using execFile for shell injection safety)
// ---------------------------------------------------------------------------
function startService() {
    const platform = os.platform();
    // Use execFile with a fixed executable — no shell interpolation of user input
    // pythonw on Windows suppresses the console window; python3 on Unix
    const executable = platform === "win32" ? "pythonw" : "python3";
    const args = ["-m", "agenttalk.service"];
    const spawnOptions = {
        detached: true,
        stdio: "ignore",
        // On Windows, hide the console window
        ...(platform === "win32" ? { windowsHide: true } : {}),
    };
    const child = child_process.spawn(executable, args, spawnOptions);
    child.unref(); // Detach from parent process
    child.on("error", () => {
        vscode.window.showErrorMessage("AgentTalk: Failed to start service. " +
            "Ensure agenttalk is installed (pip install agenttalk) and run: python -m agenttalk.service");
    });
    // Poll health for up to 15 seconds to confirm startup
    let attempts = 0;
    const poll = setInterval(async () => {
        attempts++;
        const online = await checkHealth();
        if (online) {
            clearInterval(poll);
            isServiceOnline = true;
            updateStatusBar();
            vscode.window.showInformationMessage("AgentTalk: Service started.");
        }
        else if (attempts >= 15) {
            clearInterval(poll);
            vscode.window.showWarningMessage("AgentTalk: Service may not have started. Check your terminal.");
        }
    }, 1000);
}
// ---------------------------------------------------------------------------
// Extension activation / deactivation
// ---------------------------------------------------------------------------
async function activate(context) {
    // Status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, STATUS_ITEM_PRIORITY);
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
    // Initial state
    updateStatusBar();
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand("agenttalk.mute", () => {
        isMuted = true;
        postConfig({ muted: true });
        updateStatusBar();
    }), vscode.commands.registerCommand("agenttalk.unmute", () => {
        isMuted = false;
        postConfig({ muted: false });
        updateStatusBar();
    }), vscode.commands.registerCommand("agenttalk.toggleMute", () => {
        isMuted = !isMuted;
        postConfig({ muted: isMuted });
        updateStatusBar();
    }), vscode.commands.registerCommand("agenttalk.speakSelection", () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }
        const selection = editor.selection;
        const text = editor.document.getText(selection);
        if (text.trim()) {
            speakText(text);
        }
        else {
            vscode.window.showInformationMessage("AgentTalk: No text selected. Select text to speak.");
        }
    }), vscode.commands.registerCommand("agenttalk.startService", () => {
        startService();
    }), vscode.commands.registerCommand("agenttalk.stopService", () => {
        postStop();
    }), vscode.commands.registerCommand("agenttalk.showStatus", async () => {
        const online = await checkHealth();
        isServiceOnline = online;
        updateStatusBar();
        const port = getPort();
        const msg = online
            ? `AgentTalk service is ONLINE on port ${port}. Muted: ${isMuted}`
            : "AgentTalk service is OFFLINE.";
        vscode.window.showInformationMessage(msg);
    }));
    // Start health check loop
    const intervalSeconds = vscode.workspace
        .getConfiguration("agenttalk")
        .get("healthCheckInterval", 30);
    startHealthCheckLoop(intervalSeconds);
    // Hook into AI extensions
    await hookAllAiExtensions();
    // Re-hook when extensions are loaded/changed (handles lazy-loaded extensions)
    context.subscriptions.push(vscode.extensions.onDidChange(async () => {
        await hookAllAiExtensions();
    }));
    // Auto-start if configured
    const autoStart = vscode.workspace
        .getConfiguration("agenttalk")
        .get("autoStart", false);
    if (autoStart && !isServiceOnline) {
        startService();
    }
}
function deactivate() {
    if (healthCheckTimer) {
        clearInterval(healthCheckTimer);
        healthCheckTimer = undefined;
    }
}
//# sourceMappingURL=extension.js.map