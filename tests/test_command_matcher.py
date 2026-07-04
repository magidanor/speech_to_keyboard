"""Unit tests for command matching -- no audio/mic required.

Run with: pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.command_matcher import CommandMatcher  # noqa: E402
from src.config import CommandConfig  # noqa: E402
from src.recognition.base import RecognitionResult  # noqa: E402


def make_matcher(cooldown_seconds: float = 0.0) -> CommandMatcher:
    commands = [
        CommandConfig(name="move_left", key="left", phrases=["left", "go left"], rhino_intent="moveLeft"),
        CommandConfig(name="move_right", key="right", phrases=["right", "go right"], rhino_intent="moveRight"),
        CommandConfig(name="jump", key="space", phrases=["jump"], rhino_intent="jump"),
    ]
    return CommandMatcher(commands, cooldown_seconds=cooldown_seconds)


def test_exact_phrase_match():
    matcher = make_matcher()
    command = matcher.match(RecognitionResult(is_final=True, text="jump"))
    assert command is not None and command.name == "jump"


def test_phrase_with_noise_words_matches_via_substring():
    matcher = make_matcher()
    command = matcher.match(RecognitionResult(is_final=True, text="please go left now"))
    assert command is not None and command.name == "move_left"


def test_unrecognized_phrase_does_not_match():
    matcher = make_matcher()
    assert matcher.match(RecognitionResult(is_final=True, text="banana")) is None


def test_intent_match_for_rhino_style_result():
    matcher = make_matcher()
    command = matcher.match(RecognitionResult(is_final=True, intent="moveRight"))
    assert command is not None and command.name == "move_right"


def test_non_final_result_is_still_matchable_if_passed_in():
    # CommandMatcher itself doesn't inspect is_final -- callers (activation
    # modes) are responsible for only calling match() on final results.
    matcher = make_matcher()
    command = matcher.match(RecognitionResult(is_final=False, text="jump"))
    assert command is not None and command.name == "jump"


def test_cooldown_blocks_rapid_repeats():
    matcher = make_matcher(cooldown_seconds=10.0)
    result = RecognitionResult(is_final=True, text="jump")
    assert matcher.match(result) is not None
    assert matcher.match(result) is None  # second call within cooldown window


def test_all_phrases_returns_normalized_list():
    matcher = make_matcher()
    phrases = matcher.all_phrases()
    assert "jump" in phrases
    assert "go left" in phrases


def test_overlapping_phrases_prefer_the_longest_match():
    # "stop" and "stop the music" both contain-match "please stop the music"
    # -- the longer, more specific phrase should win.
    commands = [
        CommandConfig(name="stop", key="s", phrases=["stop", "halt"]),
        CommandConfig(name="stop_music", key="m", phrases=["stop the music"]),
    ]
    matcher = CommandMatcher(commands, cooldown_seconds=0.0)
    command = matcher.match(RecognitionResult(is_final=True, text="please stop the music"))
    assert command is not None and command.name == "stop_music"

    # Plain "stop" with nothing else should still hit the shorter command.
    matcher2 = CommandMatcher(commands, cooldown_seconds=0.0)
    command2 = matcher2.match(RecognitionResult(is_final=True, text="stop"))
    assert command2 is not None and command2.name == "stop"
