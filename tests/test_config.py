"""Tests for config loading."""

import os
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULTS, load_config, validate_config


class TestLoadConfig:
    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.delenv("TICKY_PAT", raising=False)
        monkeypatch.delenv("TICKY_ORG", raising=False)
        monkeypatch.delenv("TICKY_PROJECT", raising=False)
        monkeypatch.delenv("TICKY_WORK_ITEM_TYPE", raising=False)
        config = load_config()
        assert config["work_item_type"] == "Issue"
        assert config["pat"] == ""

    def test_cli_overrides(self):
        config = load_config({"pat": "test-pat", "org": "myorg", "project": "myproj"})
        assert config["pat"] == "test-pat"
        assert config["org"] == "myorg"

    def test_none_cli_values_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.delenv("TICKY_PAT", raising=False)
        monkeypatch.delenv("TICKY_ORG", raising=False)
        config = load_config({"pat": None, "org": None})
        assert config["pat"] == ""  # default, not None

    def test_env_vars(self, monkeypatch):
        monkeypatch.setenv("TICKY_PAT", "env-pat")
        monkeypatch.setenv("TICKY_ORG", "env-org")
        config = load_config()
        assert config["pat"] == "env-pat"
        assert config["org"] == "env-org"

    def test_cli_beats_env(self, monkeypatch):
        monkeypatch.setenv("TICKY_PAT", "env-pat")
        config = load_config({"pat": "cli-pat"})
        assert config["pat"] == "cli-pat"

    def test_ini_file_loaded(self, tmp_path, monkeypatch):
        conf = tmp_path / ".ticky.conf"
        conf.write_text(textwrap.dedent("""\
            [default]
            pat = file-pat
            org = file-org
            project = file-proj
        """))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = load_config()
        assert config["pat"] == "file-pat"
        assert config["org"] == "file-org"

    def test_named_profile(self, tmp_path, monkeypatch):
        conf = tmp_path / ".ticky.conf"
        conf.write_text(textwrap.dedent("""\
            [default]
            pat = default-pat
            org = default-org
            project = default-proj

            [engineering]
            project = EngProject
            work_item_type = Task
        """))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config = load_config(profile="engineering")
        assert config["pat"] == "default-pat"  # inherited
        assert config["project"] == "EngProject"  # overridden
        assert config["work_item_type"] == "Task"

    def test_invalid_profile_raises(self, tmp_path, monkeypatch):
        conf = tmp_path / ".ticky.conf"
        conf.write_text("[default]\npat = x\n")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with pytest.raises(ValueError, match="not found"):
            load_config(profile="nonexistent")


class TestValidateConfig:
    def test_valid_config(self):
        errors = validate_config({"pat": "x", "org": "o", "project": "p"})
        assert errors == []

    def test_missing_pat(self):
        errors = validate_config({"pat": "", "org": "o", "project": "p"})
        assert any("PAT" in e for e in errors)

    def test_missing_org(self):
        errors = validate_config({"pat": "x", "org": "", "project": "p"})
        assert any("organization" in e for e in errors)

    def test_missing_project(self):
        errors = validate_config({"pat": "x", "org": "o", "project": ""})
        assert any("project" in e for e in errors)

    def test_all_missing(self):
        errors = validate_config({"pat": "", "org": "", "project": ""})
        assert len(errors) == 3
