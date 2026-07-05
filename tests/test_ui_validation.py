"""Unit tests for the command-editor's server-side validation
(src/ui/server.py's `_validate_commands`) - no Flask server, mic, or model
needs to be running.

Requires `flask` and `ruamel.yaml` (installed by `./setup.sh`); skipped
automatically if they're not available, e.g. in a minimal environment that
only cares about the core recognition/matching logic.

Run with: pytest tests/
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("flask")
pytest.importorskip("ruamel.yaml")

from src.ui.server import _validate_commands  # noqa: E402


def test_valid_commands_pass_through_cleaned_up():
    cleaned = _validate_commands(
        [{"name": "go_under_tree", "phrases": ["under the tree", " go under the tree "], "key": "down"}]
    )
    assert cleaned == [
        {
            "name": "go_under_tree",
            "phrases": ["under the tree", "go under the tree"],
            "rhino_intent": None,
            "key": "down",
        }
    ]


def test_empty_list_rejected():
    with pytest.raises(ValueError):
        _validate_commands([])


def test_missing_name_rejected():
    with pytest.raises(ValueError):
        _validate_commands([{"key": "a"}])


def test_missing_key_rejected():
    with pytest.raises(ValueError):
        _validate_commands([{"name": "jump", "phrases": ["jump"]}])


def test_duplicate_name_rejected():
    with pytest.raises(ValueError):
        _validate_commands(
            [
                {"name": "a", "key": "x", "phrases": ["a"]},
                {"name": "a", "key": "y", "phrases": ["b"]},
            ]
        )


def test_no_phrases_and_no_intent_rejected():
    with pytest.raises(ValueError):
        _validate_commands([{"name": "a", "key": "x", "phrases": []}])


def test_rhino_intent_alone_is_sufficient():
    cleaned = _validate_commands([{"name": "jump", "key": "space", "phrases": [], "rhino_intent": "jump"}])
    assert cleaned[0]["rhino_intent"] == "jump"


def test_longer_sentence_phrase_preserved():
    cleaned = _validate_commands([{"name": "over_hill", "phrases": ["over the hill"], "key": "up"}])
    assert cleaned[0]["phrases"] == ["over the hill"]
