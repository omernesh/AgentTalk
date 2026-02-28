---
phase: quick-6
plan: "01"
subsystem: agenttalk
tags: [latency, tts, streaming, hooks, post-tool-use]
dependency_graph:
  requires: []
  provides: [sentence-level-tts-streaming, post-tool-use-early-speaking]
  affects: [agenttalk/tts_worker.py, agenttalk/service.py, agenttalk/hooks/post_tool_use_hook.py, C:/Users/omern/.claude/settings.json]
tech_stack:
  added: []
  patterns: [per-sentence-queue-items, jsonl-transcript-parsing, terminal-punctuation-filter]
key_files:
  created:
    - agenttalk/hooks/post_tool_use_hook.py
  modified:
    - agenttalk/tts_worker.py
    - agenttalk/service.py
    - C:/Users/omern/.claude/settings.json
decisions:
  - TTS_QUEUE items changed from list[str] batches to individual str sentences — duck/unduck per sentence accepted as correctness trade-off for immediate first-sentence playback
  - _is_substantial threshold set at 80 chars + terminal punctuation to prevent speaking one-liners like "Reading file..." during rapid tool use
metrics:
  duration: "3 min"
  completed_date: "2026-02-28"
  tasks_completed: 2
  files_changed: 4
---

# Quick Task 6: AgentTalk Latency Optimization Summary

**One-liner:** Sentence-level TTS streaming (queue str items individually, not list batches) plus PostToolUse hook that speaks substantial partial assistant messages between tool calls.

## What Was Built

### Task 1: Sentence-level TTS streaming

Changed the TTS pipeline so each sentence is enqueued as a single `str` rather than the entire `list[str]` batch as one queue item.

**agenttalk/tts_worker.py:**
- `TTS_QUEUE` maxsize increased from 3 to 10 (accommodates individual sentences)
- `_tts_worker` rewritten: dequeues `sentence: str` per iteration, no inner for-loop
- Duck/unduck and cue playback now happen per sentence
- Module docstring updated to reflect str items and maxsize=10

**agenttalk/service.py:**
- `/speak` handler replaced single `put_nowait(sentences)` with a per-sentence loop
- Drops remaining sentences gracefully when queue fills mid-loop
- Returns `{"status": "queued", "sentences": N, "dropped": M}` with count info
- Returns 429 only if zero sentences were queued

**Effect:** First audio begins playing as soon as sentence 1 is synthesized. Sentences 2+ wait in the queue. Previously all sentences were bundled into one queue item, so audio didn't start until the worker dequeued the entire batch.

### Task 2: PostToolUse early speaking hook

**agenttalk/hooks/post_tool_use_hook.py (new):**
- Reads `transcript_path` from PostToolUse stdin payload
- `_extract_assistant_text()`: walks JSONL lines in reverse, unwraps message envelopes, extracts text from `str` content or `list` of `type=text` blocks
- `_read_speech_mode()` and `_config_path()` copied verbatim from stop_hook.py
- `_is_substantial()`: returns True only if `len(stripped) > 80 AND stripped[-1] in ('.', '!', '?')`
- Silently exits when speech_mode is semi-auto
- POSTs substantial text to `http://localhost:5050/speak` via urllib.request
- Uses `pythonw.exe` (no console window), `async: true`, `timeout: 10`

**C:/Users/omern/.claude/settings.json:**
- Added post_tool_use_hook as second entry in existing PostToolUse hooks array
- gsd-context-monitor preserved as first entry
- Stop and SessionStart hooks unchanged

**Effect:** Users hear substantial partial responses while Claude is still running tools in auto mode, before the Stop hook fires at the end.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | ad185e9 | feat(quick-6): sentence-level TTS streaming - queue str items individually |
| 2 | 33c20ed | feat(quick-6): add PostToolUse early-speaking hook |

## Deviations from Plan

None - plan executed exactly as written.

## Success Criteria Check

- [x] TTS_QUEUE.maxsize == 10 and queue items are str (not list)
- [x] /speak handler loops enqueuing sentences one by one; drops remainder gracefully on full queue
- [x] _tts_worker dequeues str and handles duck/unduck per sentence; no inner for-loop over a list
- [x] post_tool_use_hook.py passes all automated verify checks
- [x] settings.json PostToolUse has both gsd-context-monitor and post_tool_use_hook entries
- [x] _is_substantial returns False for text under 80 chars or without terminal punctuation
- [x] Hook exits silently when speech_mode is semi-auto
- [x] All other hooks (Stop, SessionStart) remain unchanged in settings.json

## Self-Check: PASSED
