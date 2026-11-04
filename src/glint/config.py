"""The config file: where the database is, which model to use and what queries may do.

It holds credentials, so it's kept out of git; glint.example.toml shows the format.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from glint.postgres.effects import Effect


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A libpq connection string with credentials: a postgresql:// URL or key=value pairs.
    connection: str


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_key: str
    name: str


class EffectsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The effects a query may have. A query with any other effect is rejected.
    allow: list[Effect]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: DatabaseConfig
    model: ModelConfig
    effects: EffectsConfig
    # A file to keep the conversation in across restarts. Without it, history is kept only in memory.
    history: Path | None = None


def load_config(path: Path) -> Config:
    with path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))
