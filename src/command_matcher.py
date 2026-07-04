"""Maps a RecognitionResult (free text or an intent name) to a configured command."""
import re
import time
from typing import Dict, List, Optional

from .config import CommandConfig
from .recognition.base import RecognitionResult

_WORD_RE = re.compile(r"[a-z0-9']+")


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


class CommandMatcher:
    def __init__(self, commands: List[CommandConfig], cooldown_seconds: float = 0.3):
        self._commands = commands
        self._cooldown = cooldown_seconds
        self._last_fired_at = 0.0

        self._phrase_to_command: Dict[str, CommandConfig] = {}
        self._intent_to_command: Dict[str, CommandConfig] = {}
        for cmd in commands:
            for phrase in cmd.phrases:
                self._phrase_to_command[_normalize(phrase)] = cmd
            if cmd.rhino_intent:
                self._intent_to_command[cmd.rhino_intent] = cmd

    def all_phrases(self) -> List[str]:
        """Normalized phrase list, e.g. for building a Vosk grammar."""
        return list(self._phrase_to_command.keys())

    def match(self, result: RecognitionResult) -> Optional[CommandConfig]:
        command = self._lookup(result)
        if command is None:
            return None

        now = time.monotonic()
        if now - self._last_fired_at < self._cooldown:
            return None
        self._last_fired_at = now
        return command

    def _lookup(self, result: RecognitionResult) -> Optional[CommandConfig]:
        if result.intent is not None:
            return self._intent_to_command.get(result.intent)

        if not result.text:
            return None

        normalized = _normalize(result.text)
        command = self._phrase_to_command.get(normalized)
        if command is not None:
            return command

        # Fall back to substring containment so e.g. "please go left now"
        # still matches the "left" command. Multiple phrases can contain
        # each other (e.g. "stop" and "stop the dog now" both match "stop
        # the dog") -- prefer the longest one since it's the most specific.
        best_phrase = None
        best_command = None
        for phrase, cmd in self._phrase_to_command.items():
            if not phrase:
                continue
            if phrase in normalized or normalized in phrase:
                if best_phrase is None or len(phrase) > len(best_phrase):
                    best_phrase = phrase
                    best_command = cmd
        return best_command
