"""Configuration loading for ticky CLI.

Resolution order (later wins):
  1. ~/.ticky.conf [default] profile
  2. ~/.ticky.conf [named] profile (if --profile used)
  3. ./.ticky.conf [default] profile
  4. ./.ticky.conf [named] profile (if --profile used)
  5. Environment variables (TICKY_PAT, TICKY_ORG, TICKY_PROJECT, TICKY_WORK_ITEM_TYPE)
  6. CLI flags (--org, --project, --type, --pat)
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


def _read_ini(path: Path, profile: str | None = None) -> dict:
    """Read an INI config file and return merged values from [default] + [profile]."""
    if not path.is_file():
        return {}
    cp = configparser.ConfigParser()
    cp.read(path)

    result = {}

    # Always load [default] first
    if "default" in cp:
        result.update({k: v for k, v in cp["default"].items() if v})

    # Layer the named profile on top (inherits from default)
    if profile and profile != "default" and profile in cp:
        result.update({k: v for k, v in cp[profile].items() if v})
    elif profile and profile != "default" and profile not in cp:
        raise ValueError(
            f"Profile '{profile}' not found in {path}. "
            f"Available: {[s for s in cp.sections()]}"
        )

    return result


def load_config(cli_args: dict | None = None, profile: str | None = None) -> dict:
    """Merge config from all sources and return a flat dict.

    Args:
        cli_args: dict of CLI-provided overrides (keys matching DEFAULTS).
                  None values are ignored.
        profile: named profile to load from config files.
    """
    config = dict(DEFAULTS)

    # Layer 1-2: user-level config (default + profile)
    config.update(_read_ini(Path.home() / ".ticky.conf", profile))

    # Layer 3-4: project-level config (default + profile)
    config.update(_read_ini(Path.cwd() / ".ticky.conf", profile))

    # Layer 5: environment variables
    for key, env_var in ENV_MAP.items():
        val = os.environ.get(env_var)
        if val:
            config[key] = val

    # Layer 6: CLI flags
    if cli_args:
        for key, val in cli_args.items():
            if val is not None and key in DEFAULTS:
                config[key] = val

    return config


def list_profiles() -> list[dict]:
    """Return a list of profiles found in config files with their settings."""
    profiles = []
    for path in [Path.home() / ".ticky.conf", Path.cwd() / ".ticky.conf"]:
        if not path.is_file():
            continue
        cp = configparser.ConfigParser()
        cp.read(path)
        for section in cp.sections():
            profiles.append({
                "name": section,
                "source": str(path),
                "org": cp[section].get("org", ""),
                "project": cp[section].get("project", ""),
                "work_item_type": cp[section].get("work_item_type", ""),
                "has_pat": bool(cp[section].get("pat", "")),
            })
    return profiles


def validate_config(config: dict) -> list[str]:
    """Return a list of error messages for missing required fields."""
    errors = []
    if not config.get("pat"):
        errors.append(
            "No PAT configured. Set in ~/.ticky.conf [default] pat=, "
            "TICKY_PAT env var, or --pat flag."
        )
    if not config.get("org"):
        errors.append(
            "No organization configured. Set in ~/.ticky.conf [default] org=, "
            "TICKY_ORG env var, or --org flag."
        )
    if not config.get("project"):
        errors.append(
            "No project configured. Set in ~/.ticky.conf [default] project=, "
            "TICKY_PROJECT env var, or --project flag."
        )
    return errors
