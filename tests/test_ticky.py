"""Tests for ticky core functions."""

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import sys
import os

# Add project root to path so we can import ticky
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ticky import (
    _ADO_DONE_STATES,
    _format_frontmatter_value,
    build_payload,
    parse_md_ticket,
    sync_ticket,
    update_md_frontmatter,
)


# ── build_payload ────────────────────────────────────────────────────────────


class TestBuildPayload:
    def test_title_only(self):
        ops = build_payload({"title": "Fix the bug"})
        assert len(ops) == 1
        assert ops[0] == {"op": "add", "path": "/fields/System.Title", "value": "Fix the bug"}

    def test_all_standard_fields(self):
        ticket = {
            "title": "My ticket",
            "description": "<p>Details</p>",
            "priority": 2,
            "tags": "Tag1; Tag2",
        }
        ops = build_payload(ticket)
        assert len(ops) == 4
        paths = [op["path"] for op in ops]
        assert "/fields/System.Title" in paths
        assert "/fields/System.Description" in paths
        assert "/fields/Microsoft.VSTS.Common.Priority" in paths
        assert "/fields/System.Tags" in paths

    def test_priority_cast_to_int(self):
        ops = build_payload({"title": "T", "priority": "3"})
        prio_op = [op for op in ops if "Priority" in op["path"]][0]
        assert prio_op["value"] == 3

    def test_extra_fields_passthrough(self):
        ticket = {
            "title": "T",
            "fields": {"Custom.Field": "value"},
        }
        ops = build_payload(ticket)
        assert any(op["path"] == "/fields/Custom.Field" for op in ops)

    def test_meta_key_not_in_payload(self):
        ticket = {"title": "T", "_meta": {"status": "draft"}}
        ops = build_payload(ticket)
        # _meta should not generate any ops
        assert all("_meta" not in op["path"] for op in ops)


# ── _format_frontmatter_value ────────────────────────────────────────────────


class TestFormatFrontmatterValue:
    def test_simple_string(self):
        assert _format_frontmatter_value("hello") == "hello"

    def test_integer(self):
        assert _format_frontmatter_value(42) == "42"

    def test_float(self):
        assert _format_frontmatter_value(3.14) == "3.14"

    def test_bool_true(self):
        assert _format_frontmatter_value(True) == "true"

    def test_bool_false(self):
        assert _format_frontmatter_value(False) == "false"

    def test_string_with_colon(self):
        result = _format_frontmatter_value("key: value")
        assert result.startswith('"')

    def test_string_with_hash(self):
        result = _format_frontmatter_value("has # comment")
        assert result.startswith('"')

    def test_empty_string(self):
        result = _format_frontmatter_value("")
        assert result == '""'

    def test_none_becomes_string(self):
        result = _format_frontmatter_value(None)
        assert result == "None"


# ── parse_md_ticket ──────────────────────────────────────────────────────────


class TestParseMdTicket:
    def test_basic_ticket(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "Fix login bug"
            type: Bug
            priority: 1
            tags: "Auth; P1"
            status: draft
            ado_id: null
            ---

            <p>Description here</p>
        """))
        ticket = parse_md_ticket(str(md))
        assert ticket["title"] == "Fix login bug"
        assert ticket["type"] == "Bug"
        assert ticket["priority"] == 1
        assert ticket["description"] == "<p>Description here</p>"
        assert ticket["_meta"]["status"] == "draft"
        assert ticket["_meta"]["ado_id"] is None

    def test_meta_keys_separated(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            assigned_to: Jane
            created: 2026-01-01
            submitted: 2026-01-02
            ---

            Body
        """))
        ticket = parse_md_ticket(str(md))
        # Meta keys should not be in the ticket dict (except under _meta)
        assert "status" not in ticket
        assert "ado_id" not in ticket
        assert ticket["_meta"]["status"] == "submitted"
        assert ticket["_meta"]["ado_id"] == 5139

    def test_no_frontmatter_raises(self, tmp_path):
        md = tmp_path / "bad.md"
        md.write_text("# Just a markdown file\nNo frontmatter here.")
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            parse_md_ticket(str(md))

    def test_missing_title_raises(self, tmp_path):
        md = tmp_path / "notitle.md"
        md.write_text(textwrap.dedent("""\
            ---
            type: Issue
            status: draft
            ---

            Body
        """))
        with pytest.raises(ValueError, match="missing required field 'title'"):
            parse_md_ticket(str(md))

    def test_empty_body(self, tmp_path):
        md = tmp_path / "nobody.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "No body ticket"
            status: draft
            ---

        """))
        ticket = parse_md_ticket(str(md))
        assert "description" not in ticket

    def test_body_with_triple_dashes(self, tmp_path):
        """Body containing --- should not break parsing."""
        md = tmp_path / "dashes.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "Dashes test"
            status: draft
            ---

            Some content
            ---
            More content after dashes
        """))
        ticket = parse_md_ticket(str(md))
        assert "---" in ticket["description"]
        assert "More content after dashes" in ticket["description"]


# ── update_md_frontmatter ────────────────────────────────────────────────────


class TestUpdateMdFrontmatter:
    def test_update_existing_key(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body here
        """))
        update_md_frontmatter(str(md), {"status": "done"})
        text = md.read_text()
        assert "status: done" in text
        assert "status: submitted" not in text
        assert "Body here" in text
        assert "ado_id: 5139" in text

    def test_add_new_key(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            ---

            Body
        """))
        update_md_frontmatter(str(md), {"ado_id": 9999})
        text = md.read_text()
        assert "ado_id: 9999" in text
        assert "status: draft" in text

    def test_body_preserved_exactly(self, tmp_path):
        body = "<h2>Description</h2>\n<p>Keep this exact content</p>\n---\nMore stuff\n"
        md = tmp_path / "ticket.md"
        md.write_text(f"---\ntitle: T\nstatus: draft\n---\n{body}")
        update_md_frontmatter(str(md), {"status": "done"})
        text = md.read_text()
        assert body in text

    def test_multiple_updates(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            ado_id: null
            ---

            Body
        """))
        update_md_frontmatter(str(md), {"status": "submitted", "ado_id": 1234})
        text = md.read_text()
        assert "status: submitted" in text
        assert "ado_id: 1234" in text

    def test_no_frontmatter_raises(self, tmp_path):
        md = tmp_path / "bad.md"
        md.write_text("No frontmatter")
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            update_md_frontmatter(str(md), {"status": "done"})

    def test_value_with_special_chars_quoted(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            tags: old
            ---

            Body
        """))
        update_md_frontmatter(str(md), {"tags": "Tag1; Tag2"})
        text = md.read_text()
        # Semicolon shouldn't need quoting per our implementation,
        # but let's verify the value is there
        assert "Tag1; Tag2" in text


# ── sync_ticket ──────────────────────────────────────────────────────────────


class TestSyncTicket:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def test_non_md_returns_none(self, tmp_path):
        f = tmp_path / "ticket.yaml"
        f.write_text("title: T")
        assert sync_ticket(str(f), self.MOCK_CONFIG) is None

    def test_skips_draft_status(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            ado_id: null
            ---

            Body
        """))
        assert sync_ticket(str(md), self.MOCK_CONFIG) == "skipped"

    def test_skips_done_status(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: done
            ado_id: 5139
            ---

            Body
        """))
        assert sync_ticket(str(md), self.MOCK_CONFIG) == "skipped"

    def test_skips_no_ado_id(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ---

            Body
        """))
        assert sync_ticket(str(md), self.MOCK_CONFIG) == "skipped"

    def test_invalid_ado_id(self, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: not-a-number
            ---

            Body
        """))
        result = sync_ticket(str(md), self.MOCK_CONFIG)
        assert result.startswith("error:")

    @patch("ticky.get_work_item")
    def test_updates_when_ado_done(self, mock_get, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        mock_get.return_value = {"fields": {"System.State": "Done"}}
        result = sync_ticket(str(md), self.MOCK_CONFIG)
        assert result == "updated"
        text = md.read_text()
        assert "status: done" in text

    @patch("ticky.get_work_item")
    def test_current_when_ado_not_done(self, mock_get, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        mock_get.return_value = {"fields": {"System.State": "Active"}}
        result = sync_ticket(str(md), self.MOCK_CONFIG)
        assert result == "current"

    @patch("ticky.get_work_item")
    def test_dry_run_no_write(self, mock_get, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        mock_get.return_value = {"fields": {"System.State": "Closed"}}
        result = sync_ticket(str(md), self.MOCK_CONFIG, dry_run=True)
        assert result == "updated"
        # File should NOT have been modified
        assert "status: submitted" in md.read_text()

    @patch("ticky.get_work_item")
    def test_api_error_handled(self, mock_get, tmp_path):
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        mock_get.side_effect = RuntimeError("HTTP 404: Not found")
        result = sync_ticket(str(md), self.MOCK_CONFIG)
        assert result.startswith("error:")

    def test_no_frontmatter_returns_error(self, tmp_path):
        md = tmp_path / "bad.md"
        md.write_text("Just text, no frontmatter")
        result = sync_ticket(str(md), self.MOCK_CONFIG)
        assert result.startswith("error:")


# ── _ADO_DONE_STATES ────────────────────────────────────────────────────────


class TestAdoDoneStates:
    def test_expected_states(self):
        assert "Done" in _ADO_DONE_STATES
        assert "Closed" in _ADO_DONE_STATES
        assert "Resolved" in _ADO_DONE_STATES
        assert "Removed" in _ADO_DONE_STATES

    def test_active_not_done(self):
        assert "Active" not in _ADO_DONE_STATES
        assert "New" not in _ADO_DONE_STATES
