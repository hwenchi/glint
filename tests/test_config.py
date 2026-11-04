from pathlib import Path

import pytest
from pydantic import ValidationError

from glint.config import load_config
from glint.postgres.effects import Effect

EXAMPLE = Path(__file__).parent.parent / "glint.example.toml"

DATABASE = '[database]\nconnection = "x"\n'
MODEL = '[model]\nbase_url = "u"\napi_key = "k"\nname = "n"\n'
EFFECTS = '[effects]\nallow = ["reads_data"]\n'


def test_example_is_valid():
    config = load_config(EXAMPLE)
    assert config.database.connection.startswith("postgresql://")
    assert config.model.name == "qwen3.6-35b-a3b"
    assert config.history is None
    assert config.effects.allow == [
        Effect.READS_DATA,
        Effect.READS_CATALOG,
        Effect.READS_SESSION_SETTINGS,
        Effect.READS_CLOCK,
    ]


def test_history(tmp_path):
    path = write(tmp_path, 'history = "chats/glint.json"\n' + DATABASE + MODEL + EFFECTS)
    assert load_config(path).history == Path("chats/glint.json")


def write(tmp_path, text):
    path = tmp_path / "glint.toml"
    path.write_text(text)
    return path


def test_missing_field(tmp_path):
    path = write(tmp_path, DATABASE + '[model]\nbase_url = "u"\napi_key = "k"\n' + EFFECTS)
    with pytest.raises(ValidationError, match="model.name"):
        load_config(path)


def test_unknown_field(tmp_path):
    path = write(tmp_path, '[database]\nconnection = "x"\nport = 1\n' + MODEL + EFFECTS)
    with pytest.raises(ValidationError, match="database.port"):
        load_config(path)


def test_missing_effects(tmp_path):
    path = write(tmp_path, DATABASE + MODEL)
    with pytest.raises(ValidationError, match="effects"):
        load_config(path)


def test_unknown_effect(tmp_path):
    path = write(tmp_path, DATABASE + MODEL + '[effects]\nallow = ["read_data"]\n')
    with pytest.raises(ValidationError, match="effects.allow.0"):
        load_config(path)
