"""Configuration loading for ticky CLI.

Resolution order (later wins):
  1. ~/.ticky.conf
  2. ./.ticky.conf (project-level)
  3. Environment variables (TICKY_PAT, TICKY_ORG, TICKY_PROJECT, TICKY_WORK_ITEM_TYPE)
  4. CLI flags
"""

import configparser
import os
from pathlib import Path

DEFAULTS = {
    "pat": "",
    "org": "",
    "project": "",
    "work_item_type": "Issue",
}

ENV_MAP = {
    "pat": "TICKY_PAT",
    "org": "TICKY_ORG",
    "project": "TICKY_PROJECT",
    "work_item_type": "TICKY_WORK_ITEM_TYPE",
}


def _read_ini(path: Path) -> dict:
    """Read an INI config file and return the [ado] section as a dict."""
    if not path.is_file():
        return {}
    cp = configparser.ConfigParser()
    cp.read(path)
    if "ado" not in cp:
        return {}
    return {k: v for k, v in cp["ado"].items() if v}


def load_config(cli_args: dict | None = None) -> dict:
    """Merge config from all sources and return a flat dict.

    Args:
        cli_args: dict of CLI-provided overrides (keys matching DEFAULTS).
                  None values are ignored.
    """
    config = dict(DEFAULTS)

    # Layer 1: user-level config
    config.update(_read_ini(Path.home() / ".ticky.conf"))

    # Layer 2: project-level config
    config.update(_read_ini(Path.cwd() / ".ticky.conf"))

    # Layer 3: environment variables
    for key, env_var in ENV_MAP.items():
        val = os.environ.get(env_var)
        if val:
            config[key] = val

    # Layer 4: CLI flags
    if cli_args:
        for key, val in cli_args.items():
            if val is not None and key in DEFAULTS:
                config[key] = val

    return config


def validate_config(config: dict) -> list[str]:
    """Return a list of error messages for missing required fields."""
    errors = []
    if not config.get("pat"):
        errors.append(
            "No PAT configured. Set in ~/.ticky.conf [ado] pat=, "
            "TICKY_PAT env var, or --pat flag."
        )
    if not config.get("org"):
        errors.append(
            "No organization configured. Set in ~/.ticky.conf [ado] org=, "
            "TICKY_ORG env var, or --org flag."
        )
    if not config.get("project"):
        errors.append(
            "No project configured. Set in ~/.ticky.conf [ado] project=, "
            "TICKY_PROJECT env var, or --project flag."
        )
    return errors
