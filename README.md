# speech_to_text

Turns spoken commands into keyboard key presses. Say "jump" or "under the tree" and the matching key gets pressed in whatever window is focused - built for controlling a game (e.g. a Unity game) by voice, using a fixed set of recognized commands rather than open-ended dictation.

## Getting started

### Prerequisites

- **Python 3.9 or newer.** Check with `python3 --version` (macOS/Linux) or `python --version` (Windows) in a terminal. If it's missing or too old, download it from [python.org/downloads](https://www.python.org/downloads/) (on Windows, tick "Add python.exe to PATH" during install).
- **A working microphone**, and an internet connection the first time it starts (to install dependencies and download the ~40MB speech model - no internet is needed after that).

### 1. Start the app

Double-click:

- **macOS**: `Start Speech To Keyboard.app`
- **Windows**: `Start Speech To Keyboard.vbs`

No terminal or console window opens for regular use. The very first time, it'll notice setup hasn't been done yet and offer to do it (a window opens just for that one-time step, showing progress); after that, every double-click just opens straight to the app in your browser.

<details>
<summary>Prefer to run setup yourself instead of being prompted? (optional)</summary>

This is exactly what the launcher above does automatically on first run, if you'd rather do it directly:

- **macOS/Linux**: open a terminal in this folder and run `./setup.sh`.
- **Windows**: double-click `setup.bat` (a window opens showing progress - press Enter when it says "Setup complete").

Either way, this creates a self-contained environment, installs everything the app needs, and downloads the speech recognition model. It's safe to run again later (e.g. after an update) - it skips anything already done.

</details>

### 2. The Run tab

This is where recognition actually happens.

- **Start** turns on voice recognition. Say one of the configured commands and the matching key gets pressed.
- **Stop** turns it off again, without closing the app.
- **Quit app** closes the whole app. Since there's no window or terminal to close otherwise, this is the intended way to shut it down.
- The **activity log** shows each command as it's recognized, so you can see it's working.

### 3. The Config tab

This is where the list of voice commands lives.

- Each row is one command: a **name**, one or more **phrases** that trigger it, and the **key** it presses.
- **+ Add command** adds a row; the **x** button removes one; **Save to config.yaml** saves your changes.
- **Test a typed phrase** checks whether a phrase matches a command, without needing to speak.
- **Test by speaking** actually listens through the microphone for a few seconds and shows what it heard and whether it matched - the most reliable way to check a phrase will really work in practice.

## Troubleshooting

**Getting a 403, or the page won't load, when the app starts.** Something else is very likely already listening on the same port. The most common cause on macOS is AirPlay Receiver, which by default listens on port 5000 (which is specifically why this app uses port 8765 instead) - but any other local dev server, or a previous copy of this app that didn't shut down cleanly, can cause the same symptom. To check:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

If that shows an unexpected process, quit it, or run this app on a different port instead: `./app.sh --port 8080` (note: the double-click launchers assume the default port, so after changing it, start the app from a terminal instead).

**Nothing happens when a command should fire.** Check the Run tab's activity log for a "heard ... but no command matched" message versus nothing at all - the former means recognition is working but the phrase needs tuning (use the Config tab's testers); the latter usually means audio isn't reaching the app at all (check microphone permissions, and that the right input device is selected as the system's default mic).

**Keys aren't registering in the target window/game at all.** Run `python scripts/test_keyboard.py` from a terminal with that window focused, to check whether it's a key-injection problem or a recognition problem.

**Keys come out wrong when a non-English keyboard layout is active** (e.g. Hebrew). See [Keyboard layouts and non-US input](#keyboard-layouts-and-non-us-input) below.

**The app won't close, or Quit doesn't seem to work.** It can be force-closed like any other stuck process: Activity Monitor on macOS, Task Manager on Windows - look for `python` or `pythonw`.

## Running from a terminal instead

Everything above also works as plain command-line tools, useful for development or for running headless. These are bash scripts - macOS/Linux have a compatible shell built in; on Windows, use Git Bash/WSL if you have it, or run `.venv\Scripts\python.exe -m src.ui.server` / `-m src.main` directly instead:

```bash
./app.sh              # same app as the double-click launchers, at http://127.0.0.1:8765
./app.sh --port 8080  # on a different port
./app.sh --config other.yaml
./run.sh               # the Run tab's pipeline only, no web UI, stop with Ctrl+C
./run.sh -v             # verbose logging
```

Setup by hand, without `./setup.sh`, also works:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/download_vosk_model.py
```

## Project layout

```
config.yaml                  All settings: engine, activation mode, key bindings, commands
src/
  config.py                  Loads config.yaml into dataclasses
  main.py                    run() / build_engine() / build_activation() - the core pipeline
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
setup.sh                     One-time setup (macOS/Linux): creates .venv, installs deps, downloads the model
setup.bat                    One-time setup (Windows), same as setup.sh but native - no Git Bash/WSL needed
app.sh                       Activates .venv and starts the app (Run + Config tabs)
run.sh                       Activates .venv and runs the pipeline headless, no UI
Start Speech To Keyboard.app Double-click launcher for non-technical users (macOS, no terminal)
Start Speech To Keyboard.vbs Double-click launcher for non-technical users (Windows, no terminal)
```

## Configuring commands

Each entry in `config.yaml`'s `commands:` list defines one voice command (editable via the Config tab, or by hand):

```yaml
- name: move_left
  phrases: ["left", "go left", "move left"]   # used by the Vosk engine
  rhino_intent: moveLeft                      # used by the Rhino engine
  key: left                                   # canonical key name (see below)
```

You don't need both `phrases` and `rhino_intent` - only the field the active engine uses matters, but keeping both in sync makes switching engines painless. Phrases can be longer sentences too, not just single words - e.g. `["under the tree", "go under the tree"]` - the recognizer treats the whole phrase as one matchable unit. If a heard phrase could match more than one command (e.g. "stop" and "stop the music" both match "please stop the music"), the longest, most specific phrase wins.

Canonical key names: `left right up down space enter esc tab shift_l shift_r ctrl_l ctrl_r alt_l alt_r`, plus single letters (`a`-`z`), digits (`0`-`9`), and `f1`-`f12`. These map to the right OS-level key code automatically.

## Keyboard layouts and non-US input

If the active input language is anything other than English/US (e.g. Hebrew), naive key injection breaks in a specific way: pressing "q" can come out as a completely different character in the game, because the OS translates key events through whatever layout is *currently active*.

This project avoids that by injecting the raw OS-level key code directly (Windows virtual-key codes via `SendInput`, macOS virtual keycodes via `pynput`) instead of asking the OS to "produce this character." That matters because Unity's own `KeyCode` works the same way internally - `KeyCode.Q` is a fixed code tied to a physical position on a reference US keyboard, not "whatever the Q key currently types." So switching the system's input language shouldn't affect this app's key presses at all, on Windows or macOS.

Linux is the exception: pynput's X11 backend only supports character-based key synthesis, so the same layout sensitivity can still occur there. Windows and macOS are this project's supported/tested platforms.

**Testing this with a text editor is misleading.** A text editor only ever shows the *translated character*, which is expected to change with the active input language no matter what - that's what having a different layout means, and no injection method changes it. It says nothing about whether the underlying keycode (what Unity actually reads) changed. Run `python scripts/test_keyboard_layout.py` instead: it prints both the raw keycode and the translated character for each key it sends, so you can confirm the keycode stays identical across a layout switch even though the character doesn't.

## Activation modes

Set `activation.mode` in `config.yaml`:

- **`always_on`** (default) - continuously listens. The recognizer detects when you've stopped talking on its own. Simplest to use hands-free, but background noise or a mis-heard phrase is a real risk - tune the command phrases and `matching.cooldown_seconds` if you see false triggers.
- **`push_to_talk`** - only listens while `activation.push_to_talk_key` is held down. Zero false triggers, and reacts the instant the key is released. Good if the game already dedicates a key/button to "talk."
- **`wake_word`** - say `activation.wake_word` first, then a `activation.wake_window_seconds` window opens for the actual command. Currently only supported with the Vosk engine.

## Latency tuning

Every dispatched command logs a recognition-to-dispatch time in milliseconds in the Run tab's activity log (and in the terminal, if running headless) - that's the gap between the engine finishing recognition and the key press firing, which is really telling you how the recognizer/activation mode is performing.

Things worth trying if latency feels high:

1. **Use `push_to_talk` instead of `always_on`.** Always-on waits for the recognizer's own silence detector to decide you've stopped talking; push-to-talk finalizes the instant the key is released.
2. **Keep phrases short and few per command.** Fewer/simpler phrases means faster decoding and fewer ambiguous matches.
3. **Stick with the small Vosk model** (`vosk-model-small-en-us-0.15`, the default) rather than a larger one - accuracy differences barely matter with a constrained command set, but larger models are slower per frame.
4. **Try Rhino** (see below) - its single end-to-end model tends to beat a transcribe-then-match approach for a small fixed command set.

## Switching to Picovoice Rhino

By default this project uses Vosk, which works fully offline with no account needed. Picovoice Rhino is a "speech-to-intent" engine that skips transcription entirely and maps audio straight to a command, which can push latency and accuracy further for a small fixed command set - at the cost of needing a free Picovoice account and a bit of setup:

1. `pip install pvrhino`
2. Create a free AccessKey at [console.picovoice.ai](https://console.picovoice.ai).
3. In the console, create a Speech-to-Intent context with one intent per command (`moveLeft`, `moveRight`, `jump`, `crouch`, `stop`) and the expressions that should trigger each. Download the compiled `.rhn` file for your OS.
4. In `config.yaml`: set `engine: rhino`, fill in `rhino.access_key` and `rhino.context_path`, and make sure each command's `rhino_intent` matches the intent names from your context.
5. `wake_word` activation mode isn't supported with Rhino yet - use `always_on` or `push_to_talk`.

Either engine can be used for the actual Run pipeline; the Config tab's phrase testers always use Vosk, since it can test arbitrary phrases on the fly, while Rhino's commands are fixed at context-compile time.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/
```

Tests run without a microphone, model, or OS-specific keyboard backend - they're pure logic tests, safe to run anywhere including CI.

## Next steps (not covered here)

This project stops at "a key gets pressed." Wiring it into the actual Unity game is a separate step - since it's just simulated OS-level keyboard input, any Unity project reading `Input.GetKey`/`Input.GetKeyDown` (old Input Manager) or the new Input System's keyboard device should pick it up with no game-side changes, as long as the game window has focus when a command fires.
