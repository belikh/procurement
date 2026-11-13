"""Shared fixtures. Tests run with no network and no credentials."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def recorded():
    """Return the body of a response recorded by scripts/live_smoke.py --record."""

    def load(lane: str, index: int = 0) -> str:
        path = FIXTURES / lane / f"{index:02d}.json"
        if not path.exists():
            pytest.skip(f"no recorded fixture for {lane}; run scripts/live_smoke.py --record")
        return json.loads(path.read_text())["body"]

    return load


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    """Clear every credential so a developer's .env cannot reach a test."""
    from procurement.config import settings

    for name, value in settings.model_dump().items():
        if value and any(
            part in name
            for part in ("token", "key", "secret", "cert_id", "cookies", "database_url")
        ):
            monkeypatch.setattr(settings, name, None)
