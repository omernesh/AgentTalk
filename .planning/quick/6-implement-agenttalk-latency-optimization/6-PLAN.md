---
phase: quick-6
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - agenttalk/service.py
  - agenttalk/tts_worker.py
  - agenttalk/hooks/post_tool_use_hook.py
  - C:/Users/omern/.claude/settings.json
autonomous: true
requirements: [LATENCY-01, LATENCY-02]

must_haves:
  truths:
    - First audio sentence begins playing before subsequent sentences are synthesized
    - Claude Code speaks substantial partial assistant messages between tool calls in auto mode
    - PostToolUse hook silently exits when speech_mode is semi-auto
    - PostToolUse hook silently exits when chunk under 80 chars or lacks terminal punctuation
  artifacts:
    - path: agenttalk/hooks/post_tool_use_hook.py
      provides: PostToolUse hook reads transcript JSONL and POSTs to /speak
      exports: [main]
    - path: agenttalk/service.py
      provides: Updated /speak endpoint enqueuing sentences individually
    - path: agenttalk/tts_worker.py
      provides: Updated worker accepting single-sentence str queue items
  key_links:
    - from: agenttalk/hooks/post_tool_use_hook.py
      to: http://localhost:5050/speak
      via: urllib.request POST
    - from: agenttalk/service.py
      to: agenttalk/tts_worker.TTS_QUEUE
      via: TTS_QUEUE.put_nowait(sentence) per sentence in loop
---



<objective>
Two latency optimizations:
1. Sentence-level TTS streaming: /speak enqueues each sentence as a str individually so audio
   on sentence 1 begins while subsequent sentences are still waiting in the queue.
2. PostToolUse early speaking hook: speak substantial partial assistant messages between tool
   calls, before the Stop hook fires at end of response.

Purpose: Reduce perceived latency. Users hear the start of a response sooner.
Output: Updated service.py, tts_worker.py, new post_tool_use_hook.py, updated settings.json.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
</context>

<interfaces>
From agenttalk/tts_worker.py (current state):

  TTS_QUEUE: queue.Queue = queue.Queue(maxsize=3)
  # Currently holds list[str] items (sentence batches -- NOT individual str)

  Current _tts_worker loop:
    sentences: list[str] = TTS_QUEUE.get()
    # muted check, speaking=True, pre_cue, duck
    # for sentence in sentences: synth+play
    # unduck, post_cue, finally: speaking=False, task_done()

From agenttalk/service.py /speak handler:
  sentences = preprocess(req.text)       # returns list[str]
  TTS_QUEUE.put_nowait(sentences)        # puts entire list as ONE item -- latency issue

From stop_hook.py (_config_path and _read_speech_mode to copy verbatim):

  def _config_path() -> Path:
      appdata = os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming'
      return Path(appdata) / 'AgentTalk' / 'config.json'

  def _read_speech_mode() -> str:
      try:
          data = json.loads(_config_path().read_text(encoding='utf-8'))
          return data.get('speech_mode', 'auto')
      except Exception:
          return 'auto'  # fail-open

PostToolUse hook stdin JSON (confirmed from Claude Code docs):
  {
    "session_id": "abc123",
    "transcript_path": "/path/to/transcript.jsonl",
    "hook_event_name": "PostToolUse",
    "tool_name": "Write",
    "tool_input": {...},
    "tool_response": {...},
    "tool_use_id": "toolu_01ABC123..."
  }
  CRITICAL: No last_assistant_message field exists in PostToolUse.
  Extract assistant text by reading transcript_path JSONL:
    - Walk lines in reverse to find most recent role=assistant message
    - Unwrap if msg.get('type') == 'message'
    - Content is str or list of blocks; extract type=text blocks only

Current settings.json PostToolUse (must preserve gsd-context-monitor):
  "PostToolUse": [{"hooks": [{"type":"command","command":"node ...gsd-context-monitor.js"}]}]

Python executable: C:\Python313\pythonw.exe (use pythonw.exe NOT python.exe)
New hook file: D:\docker\claudetalkgenttalk\hooks\post_tool_use_hook.py
</interfaces>
<tasks>

<task type="auto">
  <name>Task 1: Sentence-level TTS streaming -- refactor queue item from list[str] to str</name>
  <files>agenttalk/tts_worker.py, agenttalk/service.py</files>
  <action>
Change TTS pipeline so each sentence is enqueued as a single str rather than list[str] batch.
First audio plays as soon as sentence 1 is synthesized, not after the full batch is queued.

IN agenttalk/tts_worker.py:

1. Change TTS_QUEUE maxsize from 3 to 10 (now holds individual sentences):
     TTS_QUEUE: queue.Queue = queue.Queue(maxsize=10)

2. Rewrite _tts_worker to dequeue str sentences. Remove the inner for-loop.
   Handle pre/post cue and ducking per sentence (simpler, functionally correct):

     def _tts_worker(kokoro_engine) -> None:
         logging.info("TTS worker thread running.")
         while True:
             sentence: str = TTS_QUEUE.get()
             try:
                 if STATE["muted"]:
                     logging.debug("TTS: muted - skipping sentence.")
                     continue
                 if not sentence.strip():
                     continue

                 STATE["speaking"] = True
                 _swap_icon(create_image_speaking, "speaking")
                 play_cue(STATE.get("pre_cue_path"))
                 _ducker.duck()

                 engine = _get_active_engine(kokoro_engine)
                 logging.debug("TTS: synthesizing %r", sentence[:60])
                 samples, rate = engine.create(
                     sentence,
                     voice=STATE["voice"],
                     speed=STATE["speed"],
                     lang="en-us",
                 )
                 scaled = samples * STATE["volume"]
                 if STATE["volume"] > 1.0:
                     scaled = np.clip(scaled, -1.0, 1.0)
                 sd.play(scaled, samplerate=rate)
                 sd.wait()

                 _ducker.unduck()
                 play_cue(STATE.get("post_cue_path"))

             except Exception:
                 logging.exception("TTS worker error - skipping sentence.")
                 try:
                     _ducker.unduck()
                 except Exception:
                     logging.warning("Unduck on error path also failed.", exc_info=True)
             finally:
                 STATE["speaking"] = False
                 _swap_icon(create_image_idle, "idle")
                 TTS_QUEUE.task_done()

3. Update module docstring to reflect maxsize=10 and str items (not list[str]).

IN agenttalk/service.py:

Replace TTS_QUEUE.put_nowait(sentences) with a per-sentence loop.
Drop remaining sentences gracefully if queue fills mid-loop:

     queued = 0
     dropped = 0
     for sentence in sentences:
         try:
             TTS_QUEUE.put_nowait(sentence)
             queued += 1
         except queue.Full:
             dropped += 1
             logging.info(
                 "TTS queue full - dropping %d remaining sentence(s).",
                 len(sentences) - queued,
             )
             break

     if queued == 0:
         return JSONResponse(
             {"status": "dropped", "reason": "queue full"},
             status_code=429,
         )

     return JSONResponse(
         {"status": "queued", "sentences": queued, "dropped": dropped},
         status_code=202,
     )

Update the /speak endpoint docstring to mention per-sentence queuing.
  </action>
  <verify>
    <automated>python -c "
import sys; sys.path.insert(0, 'D:/docker/claudetalk')
from agenttalk.tts_worker import TTS_QUEUE
assert TTS_QUEUE.maxsize == 10, 'Expected maxsize=10 got ' + str(TTS_QUEUE.maxsize)
import inspect, agenttalk.tts_worker as w
src = inspect.getsource(w._tts_worker)
assert 'sentence: str' in src, 'Worker must declare sentence: str'
print('Task 1 checks passed.')
"</automated>
  </verify>
  <done>TTS_QUEUE maxsize=10 with str items. /speak loops enqueuing each sentence individually.
Worker processes one str sentence per iteration with duck/unduck per sentence.
First audio plays as soon as sentence 1 is synthesized.</done>
</task>

<task type="auto">
  <name>Task 2: PostToolUse early speaking hook + settings.json registration</name>
  <files>agenttalk/hooks/post_tool_use_hook.py, C:/Users/omern/.claude/settings.json</files>
  <action>
CREATE agenttalk/hooks/post_tool_use_hook.py following the structural pattern of stop_hook.py.

Key differences from stop_hook.py:
  - No stop_hook_active guard (Stop-hook specific)
  - Reads transcript_path from payload (PostToolUse has no last_assistant_message field)
  - Calls _extract_assistant_text() to parse the JSONL transcript
  - Applies _is_substantial() filter before POSTing

Module-level constants and imports (same as stop_hook.py):
  import sys, json, os, urllib.request, urllib.error
  from pathlib import Path
  SERVICE_URL = 'http://localhost:5050/speak'
  TIMEOUT_SECS = 3
  MIN_CHARS = 80

Copy _config_path() and _read_speech_mode() verbatim from stop_hook.py.

New functions to implement:

  def _extract_assistant_text(transcript_path: str) -> str:
      Read JSONL lines from transcript_path. Walk in reverse.
      Skip blank lines and lines failing json.loads.
      Unwrap: if msg.get('type') == 'message': msg = msg.get('message', msg)
      Skip if msg.get('role') != 'assistant'.
      If content is str: return content.strip().
      If content is list: join text from blocks where block['type'] == 'text'.
      Return empty string on any Exception (fail-open).

  def _is_substantial(text: str) -> bool:
      stripped = text.strip()
      return len(stripped) > MIN_CHARS and stripped[-1] in ('.', '!', '?')
      Anti-noise: prevents speaking one-liners like "Reading file..." during rapid tool use.

main() function logic:
  1. Read sys.stdin.buffer, decode utf-8, json.loads (exit 0 on failure)
  2. If _read_speech_mode() == 'semi-auto': sys.exit(0)
  3. transcript_path = payload.get('transcript_path', '')
  4. If not transcript_path: sys.exit(0)
  5. text = _extract_assistant_text(transcript_path)
  6. If not text: sys.exit(0)
  7. If not _is_substantial(text): sys.exit(0)
  8. POST text to SERVICE_URL via urllib.request (same pattern as stop_hook.py)
  9. Catch URLError silently; print unexpected errors to stderr
  10. sys.exit(0)

End file with:
  if __name__ == '__main__': main()


UPDATE C:/Users/omern/.claude/settings.json:
Read the file first (mandatory before any write). The existing PostToolUse section has ONE
matcher group with ONE hook (gsd-context-monitor.js). Add the post_tool_use_hook as a SECOND
entry in that same group's hooks array (do not create a new matcher group):

  "PostToolUse": [
    {
      "hooks": [
        {"type": "command", "command": "node \"C:/Users/omern/.claude/hooks/gsd-context-monitor.js\""},
        {
          "type": "command",
          "command": "\"C:\Python313\pythonw.exe\" \"D:\docker\claudetalk\agenttalk\hooks\post_tool_use_hook.py\"",
          "async": true,
          "timeout": 10
        }
      ]
    }
  ]

Write the complete updated settings.json using json.dumps(data, indent=2).
Preserve Stop and SessionStart hooks unchanged.
Use pythonw.exe (NOT python.exe) -- suppresses console windows, matches Stop/SessionStart pattern.
  </action>
  <verify>
    <automated>python -c "
import sys, json
sys.path.insert(0, 'D:/docker/claudetalk')
from pathlib import Path

hook = Path('D:/docker/claudetalk/agenttalk/hooks/post_tool_use_hook.py')
assert hook.exists(), 'post_tool_use_hook.py missing'
print('Hook file exists: OK')

ns = {}
exec(hook.read_text(encoding='utf-8'), ns)
long_text = 'A' * 81 + '.'
assert ns['_is_substantial'](long_text), 'Long text+period must be substantial'
short_text = 'Short.'
assert not ns['_is_substantial'](short_text), 'Short text must not be substantial'
no_punct = 'A' * 90
assert not ns['_is_substantial'](no_punct), 'No terminal punct must not be substantial'
print('_is_substantial filter: OK')

mode = ns['_read_speech_mode']()
assert mode in ('auto', 'semi-auto'), 'Bad mode: ' + str(mode)
print('_read_speech_mode=' + mode + ': OK')

settings = json.loads(Path('C:/Users/omern/.claude/settings.json').read_text(encoding='utf-8'))
hs = settings.get('hooks', settings)
post_groups = hs.get('PostToolUse', [])
all_cmds = [h.get('command', '') for g in post_groups for h in g.get('hooks', [])]
assert any('post_tool_use_hook' in c for c in all_cmds), 'Hook not in settings. Found: ' + str(all_cmds)
assert any('gsd-context-monitor' in c for c in all_cmds), 'gsd-context-monitor must be preserved'
stop_keys = [k for k in hs if 'Stop' in k or 'SessionStart' in k]
assert len(stop_keys) >= 2, 'Stop and SessionStart hooks must be preserved'
print('settings.json: both PostToolUse hooks present, Stop/SessionStart preserved: OK')
print('All checks passed.')
"</automated>
  </verify>
  <done>post_tool_use_hook.py exists with _is_substantial filter, _read_speech_mode from config file,
and _extract_assistant_text for JSONL parsing. Registered in settings.json PostToolUse alongside
gsd-context-monitor with async:true and timeout:10. All other hooks unchanged.</done>
</task>

</tasks>

<verification>
Manual smoke test after both tasks:
1. Multi-sentence /speak -- first audio starts within ~1s (sentence 1 synthesis only):
   curl -X POST http://localhost:5050/speak -H "Content-Type: application/json"         -d "{\"text\": \"Sentence one is done. Sentence two follows. Sentence three wraps up.\"}"
2. Service logs show individual str sentences being dequeued, not list objects.
3. PostToolUse test: run a Claude Code session with file writes; confirm speech between tool calls (auto mode).
4. Semi-auto suppression: POST /config {"speech_mode":"semi-auto"}, trigger tool use, verify no mid-task speech.
</verification>

<success_criteria>
- TTS_QUEUE.maxsize == 10 and queue items are str (not list)
- /speak handler loops enqueuing sentences one by one; drops remainder gracefully on full queue
- _tts_worker dequeues str and handles duck/unduck per sentence; no inner for-loop over a list
- post_tool_use_hook.py passes all automated verify checks
- settings.json PostToolUse has both gsd-context-monitor and post_tool_use_hook entries
- _is_substantial returns False for text under 80 chars or without terminal punctuation
- Hook exits silently when speech_mode is semi-auto
- All other hooks (Stop, SessionStart) remain unchanged in settings.json
</success_criteria>

<output>
After completion, create `.planning/quick/6-implement-agenttalk-latency-optimization/6-SUMMARY.md`
</output>
