"""Loads config.yaml into typed, defaulted dataclasses."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class CommandConfig:
    """One entry in the closed set of voice commands."""

    name: str
    key: str
    phrases: List[str] = field(default_factory=list)
    rhino_intent: Optional[str] = None


@dataclass
class VoskConfig:
    model_path: str = "models/vosk-model-small-en-us-0.15"
    sample_rate: int = 16000


@dataclass
class RhinoConfig:
    access_key: str = ""
    context_path: str = ""
    sensitivity: float = 0.5


@dataclass
class ActivationConfig:
    mode: str = "always_on"  # push_to_talk | always_on | wake_word
    push_to_talk_key: str = "ctrl_r"
    wake_word: str = "computer"
    wake_window_seconds: float = 4.0


@dataclass
class MatchingConfig:
    cooldown_seconds: float = 0.3
    key_press_duration: float = 0.05


@dataclass
class AppConfig:
    engine: str = "vosk"
    vosk: VoskConfig = field(default_factory=VoskConfig)
    rhino: RhinoConfig = field(default_factory=RhinoConfig)
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    commands: List[CommandConfig] = field(default_factory=list)


def load_config(path: str) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}

    commands = [CommandConfig(**c) for c in raw.get("commands", [])]

    return AppConfig(
        engine=raw.get("engine", "vosk"),
        vosk=VoskConfig(**raw.get("vosk", {})),
        rhino=RhinoConfig(**raw.get("rhino", {})),
        activation=ActivationConfig(**raw.get("activation", {})),
        matching=MatchingConfig(**raw.get("matching", {})),
        commands=commands,
    )
