---
phase: quick
plan: 2
type: execute
wave: 1
depends_on: []
files_modified:
  - agenttalk/tray.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "Tray right-click menu shows a 'Model' submenu with 'kokoro' and 'piper' options"
    - "Active model has a checkmark in the Model submenu"
    - "Voice submenu shows Kokoro voice IDs when model is kokoro"
    - "Voice submenu shows downloaded .onnx stems when model is piper (scanned at open time)"
    - "Voice submenu shows 'No Piper models found' disabled item when piper dir is empty or missing"
    - "Selecting a model updates STATE['model'] and persists to config"
    - "Selecting a piper voice sets STATE['piper_model_path'] to the full .onnx path and persists"
  artifacts:
    - path: "agenttalk/tray.py"
      provides: "Updated build_tray_icon with Model submenu and context-aware Voice submenu"
  key_links:
    - from: "tray.py _set_model()"
      to: "STATE['model']"
      via: "direct mutation + on_config_change callback"
    - from: "tray.py _voice_items() generator"
      to: "STATE['model']"
      via: "reads STATE['model'] at menu render time"
---

<objective>
Add a Model submenu to the AgentTalk system tray and make the Voice submenu context-aware.

Purpose: Users can switch between kokoro and piper TTS engines from the tray, and see only the
relevant voices for the active engine — Kokoro voice IDs for kokoro, downloaded .onnx stems for piper.

Output: Updated agenttalk/tray.py with Model submenu and dynamic Voice submenu logic.
</objective>

<execution_context>
@C:/Users/omern/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/omern/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md

Key patterns from existing tray.py code:

```python
# Dynamic submenu via callable generator — pystray evaluates at render time
pystray.MenuItem(
    "Voice",
    pystray.Menu(lambda: (
        pystray.MenuItem(voice, _set_voice(voice),
                         checked=lambda item, v=voice: state["voice"] == v,
                         radio=True)
        for voice in KOKORO_VOICES
    )),
)

# _set_voice factory pattern — captures voice in closure
def _set_voice(voice):
    def _inner(icon, item):
        state["voice"] = voice
        icon.update_menu()
    return _inner

# save_config called via on_mute_change callback from service.py
# The on_config_change parameter must be added to build_tray_icon signature
```

Existing STATE keys in tts_worker.STATE:
- `STATE["model"]`         — "kokoro" or "piper"
- `STATE["voice"]`         — Kokoro voice ID string
- `STATE["piper_model_path"]` — absolute path to .onnx or None

Piper model directory (from service.py):
```python
MODELS_DIR = Path(os.environ["APPDATA"]) / "AgentTalk" / "models"
PIPER_DIR  = MODELS_DIR / "piper"  # scan *.onnx here
```

service.py calls:
```python
icon = build_tray_icon(state=STATE, on_quit=_on_quit, on_mute_change=_on_mute_change)
```
The new `on_config_change` callback must default to None so service.py call site compiles
without modification — service.py will need a separate update to wire save_config.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Model submenu with _set_model handler to tray.py</name>
  <files>agenttalk/tray.py</files>
  <action>
In agenttalk/tray.py, make the following changes:

1. Add `on_config_change: Callable[[], None] | None = None` parameter to `build_tray_icon()`.
   - Update the docstring to document the new parameter.
   - Update the existing docstring menu structure comment to include the Model submenu.

2. Add `_set_model(model)` factory inside `build_tray_icon()` (same pattern as `_set_voice`):
   ```python
   def _set_model(model):
       def _inner(icon, item):
           state["model"] = model
           if on_config_change is not None:
               try:
                   on_config_change()
               except Exception:
                   logging.warning("on_config_change callback raised exception", exc_info=True)
           icon.update_menu()
       return _inner
   ```

3. Add a Model submenu item AFTER the Mute toggle and BEFORE the Voice submenu:
   ```python
   pystray.MenuItem(
       "Model",
       pystray.Menu(
           pystray.MenuItem(
               "kokoro",
               _set_model("kokoro"),
               checked=lambda item: state["model"] == "kokoro",
               radio=True,
           ),
           pystray.MenuItem(
               "piper",
               _set_model("piper"),
               checked=lambda item: state["model"] == "piper",
               radio=True,
           ),
       ),
   ),
   ```

4. Update the `build_tray_icon` docstring menu structure to show the new item order:
   ```
   1. Mute — toggle with checkmark
   2. Model — submenu: kokoro / piper radio buttons
   3. Voice — submenu: context-aware (see Task 2)
   4. Active: {voice} — read-only info item
   5. --- separator ---
   6. Quit
   ```

Also update service.py call site at line ~651 to pass `on_config_change`:
```python
def _on_config_change() -> None:
    """Called after model or piper voice selection from tray."""
    try:
        save_config(STATE)
    except OSError:
        logging.warning("save_config() failed after tray config change.", exc_info=True)

icon = build_tray_icon(
    state=STATE,
    on_quit=_on_quit,
    on_mute_change=_on_mute_change,
    on_config_change=_on_config_change,
)
```
  </action>
  <verify>python -c "from agenttalk.tray import build_tray_icon; print('import ok')"</verify>
  <done>
    - build_tray_icon accepts on_config_change parameter (defaults to None)
    - Model submenu appears in menu between Mute and Voice items
    - kokoro and piper are radio items with checked state tied to state["model"]
    - service.py wires _on_config_change to call save_config(STATE)
    - Import succeeds without errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Make Voice submenu context-aware based on active model</name>
  <files>agenttalk/tray.py</files>
  <action>
In agenttalk/tray.py, replace the static Voice submenu with a dynamic context-aware version.

1. Add `import os` and `from pathlib import Path` at the top of tray.py (if not already present).

2. Add a `_piper_dir()` helper at module level (outside `build_tray_icon`):
   ```python
   def _piper_dir() -> Path:
       """Return the Piper models directory path."""
       return Path(os.environ["APPDATA"]) / "AgentTalk" / "models" / "piper"
   ```

3. Replace the existing static Voice submenu with a dynamic generator that checks `state["model"]`
   at render time. Replace this block:
   ```python
   pystray.MenuItem(
       "Voice",
       pystray.Menu(lambda: (
           pystray.MenuItem(...)
           for voice in KOKORO_VOICES
       )),
   ),
   ```
   With:
   ```python
   pystray.MenuItem(
       "Voice",
       pystray.Menu(lambda: _voice_items(state)),
   ),
   ```

4. Add `_voice_items(state)` as a module-level function (NOT inside `build_tray_icon` — it needs
   access to `_set_voice_piper` which needs `on_config_change`, so keep it inside `build_tray_icon`
   as a nested function instead):

   Actually, define `_voice_items` as a nested generator function inside `build_tray_icon`, after
   all the handler definitions (`_toggle_mute`, `_set_voice`, `_set_model`, `_quit`):

   ```python
   def _set_piper_voice(stem: str, full_path: str):
       """Select a Piper voice: set piper_model_path and switch to piper model."""
       def _inner(icon, item):
           state["piper_model_path"] = full_path
           state["model"] = "piper"
           if on_config_change is not None:
               try:
                   on_config_change()
               except Exception:
                   logging.warning("on_config_change callback raised", exc_info=True)
           icon.update_menu()
       return _inner

   def _voice_items():
       """Generate Voice submenu items based on active model. Called at menu render time."""
       if state.get("model", "kokoro") == "piper":
           piper_dir = _piper_dir()
           if piper_dir.exists():
               onnx_files = sorted(piper_dir.glob("*.onnx"))
           else:
               onnx_files = []
           if not onnx_files:
               yield pystray.MenuItem(
                   "No Piper models found",
                   lambda icon, item: None,
                   enabled=False,
               )
               return
           for onnx_path in onnx_files:
               stem = onnx_path.stem
               full_path = str(onnx_path)
               yield pystray.MenuItem(
                   stem,
                   _set_piper_voice(stem, full_path),
                   checked=lambda item, p=full_path: state.get("piper_model_path") == p,
                   radio=True,
               )
       else:
           # Kokoro mode — static list
           for voice in KOKORO_VOICES:
               yield pystray.MenuItem(
                   voice,
                   _set_voice(voice),
                   checked=lambda item, v=voice: state["voice"] == v,
                   radio=True,
               )
   ```

   Then update the Voice submenu to use `_voice_items`:
   ```python
   pystray.MenuItem(
       "Voice",
       pystray.Menu(_voice_items),
   ),
   ```

   Note: `pystray.Menu` accepts a callable that returns an iterable — pass `_voice_items` directly
   (without lambda wrapper), or use `lambda: _voice_items()` — either works.

5. Update the "Active: {voice}" info item to show context-aware label:
   ```python
   pystray.MenuItem(
       lambda item: (
           f'Active: {Path(state["piper_model_path"]).stem}'
           if state.get("model") == "piper" and state.get("piper_model_path")
           else f'Active: {state["voice"]}'
       ),
       lambda icon, item: None,
       enabled=False,
   ),
   ```
   This requires `Path` to be imported (handled in step 1).
  </action>
  <verify>python -c "from agenttalk.tray import build_tray_icon, KOKORO_VOICES; icon = build_tray_icon({'muted': False, 'voice': 'af_heart', 'model': 'kokoro', 'piper_model_path': None, 'speaking': False}); print('build ok')"</verify>
  <done>
    - Voice submenu shows KOKORO_VOICES when state["model"] == "kokoro"
    - Voice submenu scans %APPDATA%/AgentTalk/models/piper/*.onnx when state["model"] == "piper"
    - "No Piper models found" disabled item appears when piper dir is empty or missing
    - Selecting a piper voice sets piper_model_path to the full .onnx path and model to "piper"
    - Active info item shows stem name for piper, voice ID for kokoro
    - build_tray_icon() constructs without error for both kokoro and piper state
  </done>
</task>

</tasks>

<verification>
After both tasks:

1. `python -c "from agenttalk.tray import build_tray_icon; b = build_tray_icon({'muted': False, 'voice': 'af_heart', 'model': 'kokoro', 'piper_model_path': None, 'speaking': False}); print('ok')"` — must print `ok`
2. `python -c "from agenttalk.tray import build_tray_icon; b = build_tray_icon({'muted': False, 'voice': 'af_heart', 'model': 'piper', 'piper_model_path': None, 'speaking': False}); print('ok')"` — must print `ok` (piper with no models, no crash)
3. `python -c "from agenttalk import service; print('service import ok')"` — must print `ok`
</verification>

<success_criteria>
- Tray menu has Model submenu with kokoro/piper radio items; active model is checked
- Voice submenu is dynamic: shows Kokoro voices when kokoro active, .onnx stems when piper active
- Selecting a piper voice also implicitly switches STATE["model"] to "piper"
- Selecting a model or piper voice persists via save_config (on_config_change callback)
- No crash when piper dir does not exist (graceful "No Piper models found" item)
- All existing tray features (mute, quit, active label) continue to work
</success_criteria>

<output>
After completion, create `.planning/quick/2-tray-icon-model-selection-and-per-model-/2-SUMMARY.md`
</output>
