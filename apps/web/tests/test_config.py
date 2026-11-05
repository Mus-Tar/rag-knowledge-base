import pytest
from pydantic import ValidationError

from rag_web.config import Settings


def test_http_timeout_defaults_to_sixty_seconds() -> None:
    settings = Settings.model_construct()

    assert settings.http_timeout_seconds == 60.0


def test_http_timeout_allows_three_hundred_seconds() -> None:
    settings = Settings(_env_file=None, http_timeout_seconds=300)

    assert settings.http_timeout_seconds == 300


def test_http_timeout_rejects_values_above_three_hundred_seconds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, http_timeout_seconds=301)
