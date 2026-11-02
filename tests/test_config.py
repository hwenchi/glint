from pathlib import Path

import pytest
from pydantic import ValidationError

from glint.config import load_config

EXAMPLE = Path(__file__).parent.parent / "glint.example.toml"


def test_example_is_valid():
    config = load_config(EXAMPLE)
    assert config.database.connection.startswith("postgresql://")
    assert config.model.name == "qwen3.6-35b-a3b"


def write(tmp_path, text):
    path = tmp_path / "glint.toml"
    path.write_text(text)
    return path


def test_missing_field(tmp_path):
    path = write(tmp_path, '[database]\nconnection = "x"\n[model]\nbase_url = "u"\napi_key = "k"\n')
    with pytest.raises(ValidationError, match="model.name"):
        load_config(path)


def test_unknown_field(tmp_path):
    path = write(tmp_path, '[database]\nconnection = "x"\nport = 1\n[model]\nbase_url = "u"\napi_key = "k"\nname = "n"\n')
    with pytest.raises(ValidationError, match="database.port"):
        load_config(path)
