# speech_to_text

Voice commands to keyboard input, for a closed set of game actions (left, right, jump, etc). This covers only the speech-to-keyboard piece — no Unity integration. The game just needs to read normal keyboard input; as far as it's concerned, a keypress is a keypress.

## Why not Whisper

Whisper (and whisper.cpp) is built for accurate, open-vocabulary transcription of full sentences, generally processed in a few-second chunks. That's the wrong tool for this job: the vocabulary here is a handful of fixed commands, and every extra millisecond of latency matters. Constraining a model to a known set of outcomes is both faster and more accurate than transcribing freely and then string-matching the result.

Two engines fit this problem well:

- **Vosk** — free, open-source, fully offline. You can pass it a JSON grammar (a list of allowed phrases) instead of an open vocabulary, which makes decoding faster and cuts down on misrecognitions. This is what the project uses by default.
- **Picovoice Rhino** — a "speech-to-intent" engine that skips transcription entirely and maps audio straight to an intent (e.g. `moveLeft`). Single end-to-end model instead of a transcribe-then-parse pipeline, so it's typically even lower latency and more accurate for a small fixed command set. Requires a free Picovoice account and training your own context file at [console.picovoice.ai](https://console.picovoice.ai).

Both are implemented behind a common interface (`src/recognition/base.py`) so you can switch by changing one line in `config.yaml`. Start with Vosk since it works out of the box with no account; move to Rhino later if you want to push latency/accuracy further.

## Project layout

```
config.yaml                  All settings: engine, activation mode, key bindings, commands
src/
  config.py                  Loads config.yaml into dataclasses
  main.py                    Entry point, wires everything together
  audio/capture.py           Microphone streaming (sounddevice)
  recognition/
    base.py                  RecognitionEngine interface + RecognitionResult
    vosk_engine.py            Grammar-constrained Vosk implementation
    rhino_engine.py           Picovoice Rhino implementation (optional)
  input/keyboard.py          Cross-platform key press injection
  activation/modes.py        always_on / push_to_talk / wake_word strategies
  command_matcher.py         Maps recognized text/intent -> configured command
scripts/
  download_vosk_model.py     Fetches a Vosk model
  test_keyboard.py           Sanity-checks key injection without any audio
tests/
  test_command_matcher.py    Unit tests for the matching logic
```

## Setup

```bash
./setup.sh
```

This creates a `.venv/` virtual environment if one doesn't already exist, installs `requirements.txt` into it, and downloads `vosk-model-small-en-us-0.15` (~40MB) into `models/` (skipped if already present). Run `./setup.sh --dev` instead to also install `requirements-dev.txt` (adds pytest). Re-running `./setup.sh` any time is safe -- it's idempotent.

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

Before wiring up speech, confirm key injection actually reaches your target window:

```bash
python scripts/test_keyboard.py
```

Focus your Unity game (or a text editor first, to sanity check) before the countdown finishes.

Then run the full pipeline:

```bash
python -m src.main --config config.yaml
```

## Configuring commands

Each entry in `config.yaml`'s `commands:` list defines one voice command:

```yaml
- name: move_left
  phrases: ["left", "go left", "move left"]   # used by the Vosk engine
  rhino_intent: moveLeft                      # used by the Rhino engine
  key: left                                   # canonical key name (see below)
```

You don't need both `phrases` and `rhino_intent` — only the field your active engine uses matters, but keeping both in sync makes switching engines painless.

Canonical key names: `left right up down space enter esc tab shift_l shift_r ctrl_l ctrl_r alt_l alt_r`, plus single letters (`a`-`z`), digits (`0`-`9`), and `f1`-`f12`. These get translated to the right backend automatically (`pydirectinput` names on Windows, `pynput` names elsewhere).

## Activation modes

Set `activation.mode` in `config.yaml`:

- **`always_on`** (default) — continuously streams the microphone. Vosk does its own silence-based endpointing, so no separate voice-activity-detection step is needed. Simplest to use hands-free, but background noise or the model mis-hearing something as a command phrase is a real risk — tune the grammar and `matching.cooldown_seconds` if you see false triggers.
- **`push_to_talk`** — only listens while `activation.push_to_talk_key` is held down. Zero false triggers and no silence-timeout to wait through, so it's usually the lowest *perceived* latency option. Good default if the game already dedicates a key/button to "talk."
- **`wake_word`** — says `activation.wake_word` first, then a `activation.wake_window_seconds` window opens for the actual command. Currently only supported with the Vosk engine (it works by swapping the recognizer's grammar at runtime).

## Latency tuning

Every dispatched command logs a `recognition-to-dispatch` time in milliseconds — that's the gap between the engine finishing recognition and the key press firing (dispatch itself is typically sub-millisecond; this number is really telling you how the recognizer/activation mode is performing). Run with `-v` for partial-result debug logging too:

```bash
python -m src.main -v
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

The command-matching tests run without a microphone, model, or OS-specific keyboard backend — they're pure logic tests, safe to run anywhere including CI.

## Next steps (not covered here)

This project stops at "a key gets pressed." Wiring it into the actual Unity game is a separate step — since it's just simulated OS-level keyboard input, any Unity project reading `Input.GetKey`/`Input.GetKeyDown` (old Input Manager) or the new Input System's keyboard device should pick it up with no game-side changes, as long as the game window has focus when a command fires.
