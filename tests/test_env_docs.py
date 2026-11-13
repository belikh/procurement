"""Every variable in .env.example is a setting, and every setting is documented."""

import re
from pathlib import Path

from pydantic import AliasChoices

from procurement.config import Settings

ROOT = Path(__file__).resolve().parent.parent


def setting_env_names() -> set[str]:
    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            names.add(str(alias.choices[0]))
        elif isinstance(alias, str):
            names.add(alias)
        else:
            names.add(field_name.upper())
    return names


def test_env_example_matches_settings():
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M))
    assert documented == setting_env_names()


def test_readme_names_only_real_variables():
    readme = (ROOT / "README.rst").read_text()
    mentioned = set(re.findall(r"``([A-Z][A-Z0-9]*_[A-Z0-9_]+)``", readme))
    aliases = {"TMAPI_API_TOKEN", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"}
    not_variables = {"EBAY_AU"}  # the eBay marketplace id
    assert mentioned - setting_env_names() - aliases - not_variables == set()
