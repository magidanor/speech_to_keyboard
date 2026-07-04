# speech_to_text

Voice commands to keyboard input, for a closed set of game actions (left, right, jump, etc). This covers only the speech-to-keyboard piece — no Unity integration. The game just needs to read normal keyboard input; as far as it's concerned, a keypress is a keypress.

## Quick start

```bash
./setup.sh   # creates .venv, installs dependencies, downloads a Vosk model
./app.sh     # opens http://127.0.0.1:5000 -- a Run tab and a Config tab
```

Before relying on speech, it's worth confirming key injection actually reaches your target window:

```bash
python scripts/test_keyboard.py
```

Focus your Unity game (or a text editor first, to sanity check) before the countdown finishes.

Setting this up for someone non-technical? See [Running it with no terminal](#running-it-with-no-terminal) -- `./setup.sh` still needs to be run once from a terminal, but after that they can just double-click a launcher.

## How it works

Whisper (and whisper.cpp) is built for accurate, open-vocabulary transcription of full sentences, generally processed in a few-second chunks. That's the wrong tool for this job: the vocabulary here is a handful of fixed commands, and every extra millisecond of latency matters. Constraining a model to a known set of outcomes is both faster and more accurate than transcribing freely and then string-matching the result.

Two engines fit this problem well:

- **Vosk** — free, open-source, fully offline. You can pass it a JSON grammar (a list of allowed phrases) instead of an open vocabulary, which makes decoding faster and cuts down on misrecognitions. This is what the project uses by default.
- **Picovoice Rhino** — a "speech-to-intent" engine that skips transcription entirely and maps audio straight to an intent (e.g. `moveLeft`). Single end-to-end model instead of a transcribe-then-parse pipeline, so it's typically even lower latency and more accurate for a small fixed command set. Requires a free Picovoice account and training your own context file at [console.picovoice.ai](https://console.picovoice.ai).

Both are implemented behind a common interface (`src/recognition/base.py`) so switching is a one-line change in `config.yaml`. Start with Vosk since it works out of the box with no account; move to Rhino later if you want to push latency/accuracy further.

## Project layout

```
config.yaml                  All settings: engine, activation mode, key bindings, commands
src/
  config.py                  Loads config.yaml into dataclasses
  main.py                    run() / build_engine() / build_activation() -- the core pipeline
  audio/capture.py           Microphone streaming (sounddevice)
  recognition/
    base.py                  RecognitionEngine interface + RecognitionResult
    vosk_engine.py            Grammar-constrained Vosk implementation
    rhino_engine.py           Picovoice Rhino implementation (optional)
  input/keyboard.py          Cross-platform key press injection by OS key code (layout-independent)
  activation/modes.py        always_on / push_to_talk / wake_word strategies (stop_event-aware)
  command_matcher.py         Maps recognized text/intent -> configured command
  ui/server.py               Flask app: Run tab (start/stop src.main.run()) + Config tab (editor/tester)
  ui/static/index.html       Frontend for the Run + Config tabs
scripts/
  download_vosk_model.py     Fetches a Vosk model
  test_keyboard.py           Sanity-checks key injection without any audio
  test_keyboard_layout.py    Diagnoses keycode-vs-character issues across input languages
tests/
  test_command_matcher.py    Unit tests for the matching logic
  test_ui_validation.py      Unit tests for the command-editor's server-side validation
setup.sh                     Creates .venv, installs deps, downloads the model
app.sh                       Activates .venv and starts the app (Run + Config tabs) -- main entry point
run.sh                       Activates .venv and runs the pipeline headless, no UI (CLI-only alternative)
Start Speech To Keyboard.app Double-click launcher for non-technical users (macOS, no terminal)
Start Speech To Keyboard.vbs Double-click launcher for non-technical users (Windows, no terminal)
```

## Setup, in detail

```bash
./setup.sh
```

Creates a `.venv/` virtual environment if one doesn't already exist, installs `requirements.txt` into it, and downloads `vosk-model-small-en-us-0.15` (~40MB) into `models/` (skipped if already present). Run `./setup.sh --dev` instead to also install `requirements-dev.txt` (adds pytest). Re-running `./setup.sh` any time is safe -- it's idempotent.

Activate the environment in new shells with:

```bash
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

Prefer to do it by hand instead of using the script? That works too:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/download_vosk_model.py
```

## Using the app: Run + Config tabs

`./app.sh` starts one web app at `http://127.0.0.1:5000` with two tabs — it's meant to feel like a single program, not two separate tools:

**Run tab** (the actual product): a status indicator, Start/Stop buttons, a "Quit app" button, and a live activity log. Clicking Start runs the speech-to-keyboard pipeline — engine, activation mode, keyboard injection, everything from `config.yaml` — inside this same server process, in a background thread. Every dispatched command shows up in the activity log (`heard "..." -> command_name (key=..., Nms)`) as it happens. Stop shuts the pipeline down cleanly and releases the microphone; Quit closes the whole app (see [Running it with no terminal](#running-it-with-no-terminal) below for why that matters).

**Config tab** (the settings/design surface):

- An editable table of commands (name, phrases, optional Rhino intent, key) with add/delete rows and a "Save to config.yaml" button. Saving preserves the comments and structure of the rest of the file.
- A **typed-phrase tester**: type any phrase and see whether it matches one of your current (even unsaved) commands — useful for quickly checking phrase wording, including longer sentences like "under the tree" or "over the hill", without needing to speak.
- A **spoken-phrase tester**: click "Record & test", speak into your mic for the configured window (default 6s), and see exactly what Vosk heard and whether it matched — the real end-to-end check, since typed-text matching can pass while the actual recognizer still mishears a longer phrase.

The Run pipeline and the spoken-phrase tester both need exclusive access to the microphone, so only one can be active at a time — starting one while the other is busy returns a clear "in use" message instead of a confusing crash. The typed-phrase tester doesn't touch the mic, so it always works, even while Run is active.

Phrase testing always goes through the Vosk engine (even if `engine: rhino` is set in config.yaml for the actual Run pipeline), since Vosk can be pointed at any ad hoc phrase list on the fly — Rhino's intents are baked into a compiled context file, so testing new phrases against it requires retraining that context in the Picovoice Console instead.

Prefer a plain terminal with no web UI? `./run.sh` runs the identical pipeline headless — the web app's Run tab is just a thin control layer on top of the same `src/main.py` code.

## Running it with no terminal

For a non-technical user, double-click:

- **macOS**: `Start Speech To Keyboard.app`
- **Windows**: `Start Speech To Keyboard.vbs`

Either one starts the app with no visible console/terminal window, waits for it to be ready, and opens it in the default browser automatically. Output is captured to `app.log` in the project folder on macOS (there's no console to print to otherwise); on Windows there's no console at all, so use `./run.sh -v` from a terminal if you need to see error details.

**Setup still needs a terminal once.** These launchers only start an already-set-up app -- `./setup.sh` (which creates `.venv`, installs dependencies, and downloads the speech model) has to be run from an actual terminal first, on both platforms. After that one-time step, the double-click launcher is all that's needed going forward.

**To close the app**, click "Quit app" in the Run tab. That's the only way to close it cleanly when launched this way, since there's no window or terminal to close otherwise -- it stops the recognition pipeline (if running) and shuts down the whole server process. If the app ever becomes unresponsive and Quit doesn't work, it can be force-closed like any other stuck process (Activity Monitor on macOS, Task Manager on Windows -- look for `python` or `pythonw`).

## Configuring commands

Each entry in `config.yaml`'s `commands:` list defines one voice command (editable via the Config tab, or by hand):

```yaml
- name: move_left
  phrases: ["left", "go left", "move left"]   # used by the Vosk engine
  rhino_intent: moveLeft                      # used by the Rhino engine
  key: left                                   # canonical key name (see below)
```

You don't need both `phrases` and `rhino_intent` — only the field your active engine uses matters, but keeping both in sync makes switching engines painless. Phrases can be longer sentences too, not just single words — e.g. `["under the tree", "go under the tree"]` — the grammar-constrained recognizer treats the whole phrase as one matchable unit. If a heard phrase could match more than one command (e.g. "stop" and "stop the music" both match "please stop the music"), the longest, most specific phrase wins.

Canonical key names: `left right up down space enter esc tab shift_l shift_r ctrl_l ctrl_r alt_l alt_r`, plus single letters (`a`-`z`), digits (`0`-`9`), and `f1`-`f12`. These map to the right OS-level key code automatically (see below).

## Keyboard layouts and non-US input

If your OS's active input language is anything other than a US layout (e.g. Hebrew), typed/character-based key injection breaks in a specific way: pressing "q" can come out as a completely different character in the game, because the OS translates key events through whatever layout is *currently active*, not the layout the config was written against.

This project avoids that by injecting the raw OS-level key code directly (Windows virtual-key codes via `SendInput`, macOS virtual keycodes via `pynput`) instead of asking the OS to "produce this character." That matters because Unity's own `KeyCode` works the same way internally -- `KeyCode.Q` is a fixed code tied to a physical position on a reference US keyboard, not "whatever the Q key currently types" -- so injecting by code, not by character, is what actually matches what Unity checks. In other words: switching your system to Hebrew input shouldn't affect this project's key presses at all, on Windows or macOS.

Linux is the exception: pynput's X11 backend only supports character-based key synthesis, so the same layout sensitivity described above can still occur there. Windows and macOS are this project's supported/tested platforms, so this hasn't been a priority to fix for X11.

**Testing this with a text editor is misleading.** A text editor only ever shows you the *translated character*, which is expected to change with your active input language no matter what -- that's what having a different layout means, and no injection method changes it. It says nothing about whether the underlying keycode (what Unity actually reads) changed. Run `python scripts/test_keyboard_layout.py` instead: it prints both the raw keycode and the translated character for each key it sends, so you can confirm the keycode stays identical across a layout switch even though the character doesn't (or, if the keycode does change, that's a real bug worth reporting).

## Activation modes

Set `activation.mode` in `config.yaml`:

- **`always_on`** (default) — continuously streams the microphone. Vosk does its own silence-based endpointing, so no separate voice-activity-detection step is needed. Simplest to use hands-free, but background noise or the model mis-hearing something as a command phrase is a real risk — tune the grammar and `matching.cooldown_seconds` if you see false triggers.
- **`push_to_talk`** — only listens while `activation.push_to_talk_key` is held down. Zero false triggers and no silence-timeout to wait through, so it's usually the lowest *perceived* latency option. Good default if the game already dedicates a key/button to "talk."
- **`wake_word`** — says `activation.wake_word` first, then a `activation.wake_window_seconds` window opens for the actual command. Currently only supported with the Vosk engine (it works by swapping the recognizer's grammar at runtime).

## Latency tuning

Every dispatched command logs a recognition-to-dispatch time in milliseconds — that's the gap between the engine finishing recognition and the key press firing (dispatch itself is typically sub-millisecond; this number is really telling you how the recognizer/activation mode is performing). The Run tab's activity log shows this per command too. For partial-result debug logging (terminal only), run headless with `-v`:

```bash
./run.sh -v
```

Things worth trying if latency feels high:

1. **Use `push_to_talk` instead of `always_on`.** Always-on waits for Vosk's internal silence detector to decide you've stopped talking; push-to-talk finalizes the instant you release the key.
2. **Keep the grammar small.** Fewer/simpler phrases per command means faster decoding and fewer ambiguous matches.
3. **Stick with the small Vosk model** (`vosk-model-small-en-us-0.15`) rather than the large one — accuracy differences barely matter with a constrained grammar, but the large model is much slower per frame.
4. **Try Rhino.** If Vosk's latency isn't enough, Rhino's single end-to-end model tends to beat the transcribe-then-match approach.
5. **Lower `preferred_frame_bytes`** (edit `VoskEngine.__init__`) for smaller audio chunks — trades a bit of CPU overhead for snappier partial/final results.

## Switching to Picovoice Rhino

1. `pip install pvrhino`
2. Create a free AccessKey at [console.picovoice.ai](https://console.picovoice.ai).
3. In the console, create a Speech-to-Intent context with one intent per command (`moveLeft`, `moveRight`, `jump`, `crouch`, `stop`) and the expressions you want to trigger each. Download the compiled `.rhn` file for your OS.
4. In `config.yaml`: set `engine: rhino`, fill in `rhino.access_key` and `rhino.context_path`, and make sure each command's `rhino_intent` matches the intent names from your context.
5. `wake_word` activation mode isn't supported with Rhino yet — use `always_on` or `push_to_talk`.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Tests run without a microphone, model, or OS-specific keyboard backend — they're pure logic tests, safe to run anywhere including CI.

## Next steps (not covered here)

This project stops at "a key gets pressed." Wiring it into the actual Unity game is a separate step — since it's just simulated OS-level keyboard input, any Unity project reading `Input.GetKey`/`Input.GetKeyDown` (old Input Manager) or the new Input System's keyboard device should pick it up with no game-side changes, as long as the game window has focus when a command fires.
