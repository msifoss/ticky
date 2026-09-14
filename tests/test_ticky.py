"""Tests for ticky core functions."""

import io
import json
import textwrap
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sys
import os

# Add project root to path so we can import ticky
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ticky import (
    _ADO_DONE_STATES,
    _META_KEYS,
    _format_frontmatter_value,
    add_comment,
    build_payload,
    cmd_attach,
    cmd_comment,
    cmd_submit,
    link_attachment,
    parse_md_ticket,
    sync_ticket,
    update_md_frontmatter,
    upload_attachment,
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


# ── upload_attachment ────────────────────────────────────────────────────────


class TestUploadAttachment:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def _make_response(self, body: dict):
        resp = MagicMock()
        resp.read.return_value = json.dumps(body).encode("utf-8")
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    @patch("ticky.urllib.request.urlopen")
    def test_returns_id_and_url(self, mock_urlopen, tmp_path):
        f = tmp_path / "screenshot.png"
        f.write_bytes(b"\x89PNG fake content")
        mock_urlopen.return_value = self._make_response(
            {"id": "abc-123", "url": "https://dev.azure.com/testorg/_apis/wit/attachments/abc-123"}
        )
        result = upload_attachment(self.MOCK_CONFIG, str(f))
        assert result["id"] == "abc-123"
        assert result["url"].endswith("/abc-123")

    @patch("ticky.urllib.request.urlopen")
    def test_url_contains_filename_and_project(self, mock_urlopen, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_bytes(b"hello")
        mock_urlopen.return_value = self._make_response({"id": "x", "url": "u"})
        upload_attachment(self.MOCK_CONFIG, str(f))
        req = mock_urlopen.call_args[0][0]
        assert "testorg" in req.full_url
        assert "TestProject" in req.full_url
        assert "fileName=notes.txt" in req.full_url
        assert "api-version=7.0" in req.full_url

    @patch("ticky.urllib.request.urlopen")
    def test_sends_raw_bytes(self, mock_urlopen, tmp_path):
        f = tmp_path / "data.bin"
        payload = b"\x00\x01\x02\x03 raw"
        f.write_bytes(payload)
        mock_urlopen.return_value = self._make_response({"id": "x", "url": "u"})
        upload_attachment(self.MOCK_CONFIG, str(f))
        req = mock_urlopen.call_args[0][0]
        assert req.data == payload
        assert req.method == "POST"
        assert req.headers.get("Content-type") == "application/octet-stream"

    @patch("ticky.urllib.request.urlopen")
    def test_auth_header_present(self, mock_urlopen, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"x")
        mock_urlopen.return_value = self._make_response({"id": "x", "url": "u"})
        upload_attachment(self.MOCK_CONFIG, str(f))
        req = mock_urlopen.call_args[0][0]
        assert req.headers.get("Authorization", "").startswith("Basic ")

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            upload_attachment(self.MOCK_CONFIG, str(tmp_path / "missing.txt"))

    @patch("ticky.urllib.request.urlopen")
    def test_http_413_gives_helpful_error(self, mock_urlopen, tmp_path):
        f = tmp_path / "huge.bin"
        f.write_bytes(b"x")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 413, "Payload Too Large", {}, io.BytesIO(b'{"message":"too big"}')
        )
        with pytest.raises(RuntimeError, match="413"):
            upload_attachment(self.MOCK_CONFIG, str(f))

    @patch("ticky.urllib.request.urlopen")
    def test_http_401_gives_auth_error(self, mock_urlopen, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"x")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, io.BytesIO(b"")
        )
        with pytest.raises(RuntimeError, match="Authentication failed"):
            upload_attachment(self.MOCK_CONFIG, str(f))


# ── link_attachment ──────────────────────────────────────────────────────────


class TestLinkAttachment:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    @patch("ticky.update_work_item")
    def test_patches_relations_add(self, mock_update):
        mock_update.return_value = {"id": 5139}
        link_attachment(self.MOCK_CONFIG, 5139, "https://dev.azure.com/attach/abc")
        patches = mock_update.call_args[0][2]
        assert len(patches) == 1
        assert patches[0]["op"] == "add"
        assert patches[0]["path"] == "/relations/-"
        assert patches[0]["value"]["rel"] == "AttachedFile"
        assert patches[0]["value"]["url"] == "https://dev.azure.com/attach/abc"

    @patch("ticky.update_work_item")
    def test_comment_included_when_given(self, mock_update):
        mock_update.return_value = {"id": 5139}
        link_attachment(self.MOCK_CONFIG, 5139, "u", comment="screenshot of bug")
        patches = mock_update.call_args[0][2]
        assert patches[0]["value"]["attributes"]["comment"] == "screenshot of bug"

    @patch("ticky.update_work_item")
    def test_no_comment_no_attributes(self, mock_update):
        mock_update.return_value = {"id": 5139}
        link_attachment(self.MOCK_CONFIG, 5139, "u")
        patches = mock_update.call_args[0][2]
        # attributes.comment should not be present when no comment given
        attributes = patches[0]["value"].get("attributes", {})
        assert "comment" not in attributes


# ── _META_KEYS includes attachment fields ────────────────────────────────────


class TestMetaKeysAttachmentFields:
    def test_attachments_is_meta(self):
        assert "attachments" in _META_KEYS

    def test_attached_is_meta(self):
        assert "attached" in _META_KEYS

    def test_attachments_not_in_build_payload(self):
        ticket = {"title": "T", "attachments": ["file1.png"], "attached": [{"id": "x"}]}
        # parse_md_ticket separates meta, but build_payload should also be safe if these
        # accidentally leak in. attachments/attached are not ADO fields.
        ops = build_payload(ticket)
        assert not any("attachments" in op["path"].lower() for op in ops)
        assert not any("attached" in op["path"].lower() for op in ops)

    def test_parse_md_puts_attachments_in_meta(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            attachments:
              - screenshot.png
              - log.txt
            ---

            body
        """))
        ticket = parse_md_ticket(str(md))
        assert "attachments" not in ticket
        assert ticket["_meta"]["attachments"] == ["screenshot.png", "log.txt"]


# ── update_md_frontmatter with attached: list ────────────────────────────────


class TestUpdateFrontmatterAttachedList:
    def test_writes_attached_list(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        attached = [
            {"file": "shot.png", "id": "abc", "url": "https://a/abc", "uploaded": "2026-09-11T12:00:00"}
        ]
        update_md_frontmatter(str(md), {"attached": attached})
        text = md.read_text()
        assert "attached:" in text
        # After write, re-parse to confirm it round-trips
        ticket = parse_md_ticket(str(md))
        assert ticket["_meta"]["attached"][0]["id"] == "abc"
        assert ticket["_meta"]["attached"][0]["url"] == "https://a/abc"

    def test_replacing_existing_list_removes_old_entries(self, tmp_path):
        """Writing attached: twice should not accumulate stale block lines."""
        md = tmp_path / "t.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            attached:
              - file: old.png
                id: old
            ---

            Body
        """))
        update_md_frontmatter(str(md), {"attached": [{"file": "new.png", "id": "new"}]})
        text = md.read_text()
        assert "old.png" not in text
        assert "id: old" not in text
        assert "new.png" in text


# ── cmd_attach ───────────────────────────────────────────────────────────────


class TestCmdAttach:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def _args(self, **overrides):
        args = MagicMock()
        args.ado_id = overrides.get("ado_id", 5139)
        args.files = overrides.get("files", [])
        args.md = overrides.get("md", None)
        args.comment = overrides.get("comment", None)
        args.verbose = False
        args.pat = None
        args.org = None
        args.project = None
        args.type = None
        args.profile = None
        args.config = None
        return args

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    def test_uploads_each_file_and_links(self, mock_upload, mock_link, mock_get_config, tmp_path, capsys):
        mock_get_config.return_value = self.MOCK_CONFIG
        f1 = tmp_path / "a.png"
        f1.write_bytes(b"a")
        f2 = tmp_path / "b.log"
        f2.write_bytes(b"b")
        mock_upload.side_effect = [
            {"id": "id-a", "url": "https://a/id-a"},
            {"id": "id-b", "url": "https://a/id-b"},
        ]
        mock_link.return_value = {"id": 5139}
        args = self._args(files=[str(f1), str(f2)])
        cmd_attach(args)
        assert mock_upload.call_count == 2
        assert mock_link.call_count == 2
        # Each link call gets the URL from the corresponding upload
        assert mock_link.call_args_list[0][0][2] == "https://a/id-a"
        assert mock_link.call_args_list[1][0][2] == "https://a/id-b"
        out = capsys.readouterr().out
        assert "id-a" in out
        assert "id-b" in out

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    def test_writes_attached_to_md_when_given(self, mock_upload, mock_link, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        f = tmp_path / "shot.png"
        f.write_bytes(b"x")
        md = tmp_path / "ticket.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: submitted
            ado_id: 5139
            ---

            Body
        """))
        mock_upload.return_value = {"id": "id-1", "url": "https://a/id-1"}
        mock_link.return_value = {"id": 5139}
        args = self._args(files=[str(f)], md=str(md))
        cmd_attach(args)
        ticket = parse_md_ticket(str(md))
        assert ticket["_meta"]["attached"][0]["id"] == "id-1"
        assert ticket["_meta"]["attached"][0]["url"] == "https://a/id-1"
        assert ticket["_meta"]["attached"][0]["file"] == "shot.png"

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    def test_comment_passed_through(self, mock_upload, mock_link, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        f = tmp_path / "shot.png"
        f.write_bytes(b"x")
        mock_upload.return_value = {"id": "id-1", "url": "u"}
        mock_link.return_value = {}
        args = self._args(files=[str(f)], comment="repro screenshot")
        cmd_attach(args)
        # link_attachment(config, id, url, comment=...)
        assert mock_link.call_args.kwargs.get("comment") == "repro screenshot" \
            or (len(mock_link.call_args.args) >= 4 and mock_link.call_args.args[3] == "repro screenshot")

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    def test_exits_nonzero_on_upload_failure(self, mock_upload, mock_link, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        f = tmp_path / "shot.png"
        f.write_bytes(b"x")
        mock_upload.side_effect = RuntimeError("HTTP 413: too big")
        args = self._args(files=[str(f)])
        with pytest.raises(SystemExit) as exc:
            cmd_attach(args)
        assert exc.value.code != 0

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    def test_partial_failure_reports_success_before_stopping(
        self, mock_upload, mock_link, mock_get_config, tmp_path, capsys
    ):
        mock_get_config.return_value = self.MOCK_CONFIG
        good = tmp_path / "good.png"
        good.write_bytes(b"g")
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"b")
        mock_upload.side_effect = [
            {"id": "good-id", "url": "u1"},
            RuntimeError("HTTP 413: too big"),
        ]
        mock_link.return_value = {}
        args = self._args(files=[str(good), str(bad)])
        with pytest.raises(SystemExit) as exc:
            cmd_attach(args)
        assert exc.value.code != 0
        out = capsys.readouterr().out
        assert "good-id" in out


# ── cmd_submit with attachments: ─────────────────────────────────────────────


class TestCmdSubmitAttachments:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def _args(self, file):
        args = MagicMock()
        args.file = str(file)
        args.assign = None
        args.dry_run = False
        args.verbose = False
        args.pat = None
        args.org = None
        args.project = None
        args.type = None
        args.profile = None
        args.config = None
        return args

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    @patch("ticky.create_work_item")
    def test_uploads_attachments_from_frontmatter(
        self, mock_create, mock_upload, mock_link, mock_get_config, tmp_path
    ):
        mock_get_config.return_value = self.MOCK_CONFIG
        # Create attachment file next to ticket
        (tmp_path / "shot.png").write_bytes(b"pixels")
        md = tmp_path / "20260101-1200-thing-draft.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "Broken login"
            status: draft
            ado_id: null
            attachments:
              - shot.png
            ---

            Body
        """))
        mock_create.return_value = {"id": 5139, "_links": {"html": {"href": "https://ado/5139"}}}
        mock_upload.return_value = {"id": "att-1", "url": "https://a/att-1"}
        mock_link.return_value = {}
        cmd_submit(self._args(md))

        assert mock_upload.call_count == 1
        # upload was called with the resolved path (relative to the .md file)
        assert mock_upload.call_args[0][1].endswith("shot.png")
        # linked to the new work item id
        assert mock_link.call_args[0][1] == 5139

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    @patch("ticky.create_work_item")
    def test_attached_list_written_back(
        self, mock_create, mock_upload, mock_link, mock_get_config, tmp_path
    ):
        mock_get_config.return_value = self.MOCK_CONFIG
        (tmp_path / "shot.png").write_bytes(b"x")
        md = tmp_path / "20260101-1200-thing-draft.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            ado_id: null
            attachments:
              - shot.png
            ---

            Body
        """))
        mock_create.return_value = {"id": 5139, "_links": {"html": {"href": ""}}}
        mock_upload.return_value = {"id": "att-1", "url": "https://a/att-1"}
        mock_link.return_value = {}
        cmd_submit(self._args(md))
        # File was renamed on submit
        renamed = tmp_path / "20260101-1200-thing-submitted.md"
        assert renamed.exists()
        ticket = parse_md_ticket(str(renamed))
        assert ticket["_meta"]["attached"][0]["id"] == "att-1"
        assert ticket["_meta"]["attached"][0]["file"] == "shot.png"

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    @patch("ticky.create_work_item")
    def test_no_attachments_frontmatter_still_submits(
        self, mock_create, mock_upload, mock_link, mock_get_config, tmp_path
    ):
        mock_get_config.return_value = self.MOCK_CONFIG
        md = tmp_path / "20260101-1200-plain-draft.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            ---

            Body
        """))
        mock_create.return_value = {"id": 5139, "_links": {"html": {"href": ""}}}
        cmd_submit(self._args(md))
        assert mock_upload.call_count == 0
        assert mock_link.call_count == 0

    @patch("ticky._get_config")
    @patch("ticky.link_attachment")
    @patch("ticky.upload_attachment")
    @patch("ticky.create_work_item")
    def test_attachment_failure_after_create_exits_nonzero(
        self, mock_create, mock_upload, mock_link, mock_get_config, tmp_path
    ):
        mock_get_config.return_value = self.MOCK_CONFIG
        (tmp_path / "shot.png").write_bytes(b"x")
        md = tmp_path / "20260101-1200-thing-draft.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: "T"
            status: draft
            attachments:
              - shot.png
            ---

            Body
        """))
        mock_create.return_value = {"id": 5139, "_links": {"html": {"href": ""}}}
        mock_upload.side_effect = RuntimeError("HTTP 413: too big")
        with pytest.raises(SystemExit) as exc:
            cmd_submit(self._args(md))
        assert exc.value.code != 0


# ── add_comment ──────────────────────────────────────────────────────────────


class TestAddComment:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def _make_response(self, body: dict):
        resp = MagicMock()
        resp.read.return_value = json.dumps(body).encode("utf-8")
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    @patch("ticky.urllib.request.urlopen")
    def test_returns_id_and_url(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response(
            {"id": 42, "url": "https://dev.azure.com/testorg/_apis/wit/workItems/5139/comments/42"}
        )
        result = add_comment(self.MOCK_CONFIG, 5139, "hello world")
        assert result["id"] == 42
        assert "/comments/42" in result["url"]

    @patch("ticky.urllib.request.urlopen")
    def test_url_contains_work_item_and_preview_version(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response({"id": 1, "url": "u"})
        add_comment(self.MOCK_CONFIG, 5139, "body")
        req = mock_urlopen.call_args[0][0]
        assert "testorg" in req.full_url
        assert "TestProject" in req.full_url
        assert "/workItems/5139/comments" in req.full_url
        # Comments API is on the preview version — required by ADO
        assert "api-version=7.0-preview" in req.full_url

    @patch("ticky.urllib.request.urlopen")
    def test_posts_json_text_body(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response({"id": 1, "url": "u"})
        add_comment(self.MOCK_CONFIG, 5139, "line one\n\nline two")
        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert req.headers.get("Content-type") == "application/json"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload == {"text": "line one\n\nline two"}

    @patch("ticky.urllib.request.urlopen")
    def test_auth_header_present(self, mock_urlopen):
        mock_urlopen.return_value = self._make_response({"id": 1, "url": "u"})
        add_comment(self.MOCK_CONFIG, 5139, "hi")
        req = mock_urlopen.call_args[0][0]
        assert req.headers.get("Authorization", "").startswith("Basic ")

    @patch("ticky.urllib.request.urlopen")
    def test_http_401_gives_auth_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {}, io.BytesIO(b"")
        )
        with pytest.raises(RuntimeError, match="Authentication failed"):
            add_comment(self.MOCK_CONFIG, 5139, "hi")

    @patch("ticky.urllib.request.urlopen")
    def test_http_404_gives_not_found_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, io.BytesIO(b'{"message":"nope"}')
        )
        with pytest.raises(RuntimeError, match="404"):
            add_comment(self.MOCK_CONFIG, 5139, "hi")


# ── cmd_comment ──────────────────────────────────────────────────────────────


class TestCmdComment:
    MOCK_CONFIG = {"pat": "fake", "org": "testorg", "project": "TestProject", "work_item_type": "Issue"}

    def _args(self, **overrides):
        args = MagicMock()
        args.ado_id = overrides.get("ado_id", 5139)
        args.body = overrides.get("body", None)
        args.body_file = overrides.get("body_file", None)
        args.verbose = False
        args.pat = None
        args.org = None
        args.project = None
        args.type = None
        args.profile = None
        args.config = None
        return args

    @patch("ticky._get_config")
    @patch("ticky.add_comment")
    def test_inline_body_posted(self, mock_add, mock_get_config, capsys):
        mock_get_config.return_value = self.MOCK_CONFIG
        mock_add.return_value = {"id": 42, "url": "https://a/42"}
        args = self._args(body="quick note")
        cmd_comment(args)
        assert mock_add.call_args[0][2] == "quick note"
        out = capsys.readouterr().out
        assert "42" in out
        assert "5139" in out

    @patch("ticky._get_config")
    @patch("ticky.add_comment")
    def test_body_file_read_and_posted(self, mock_add, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        f = tmp_path / "writeup.md"
        f.write_text("# Investigation\n\nMulti-paragraph body.\n")
        mock_add.return_value = {"id": 42, "url": "u"}
        args = self._args(body_file=str(f))
        cmd_comment(args)
        posted = mock_add.call_args[0][2]
        assert posted.startswith("# Investigation")
        assert "Multi-paragraph body." in posted

    @patch("ticky._get_config")
    @patch("ticky.add_comment")
    def test_body_file_wins_over_inline_body(self, mock_add, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        f = tmp_path / "w.md"
        f.write_text("FROM FILE")
        mock_add.return_value = {"id": 42, "url": "u"}
        args = self._args(body="INLINE", body_file=str(f))
        cmd_comment(args)
        assert mock_add.call_args[0][2] == "FROM FILE"

    @patch("ticky._get_config")
    @patch("ticky.add_comment")
    def test_missing_body_file_exits_nonzero(self, mock_add, mock_get_config, tmp_path):
        mock_get_config.return_value = self.MOCK_CONFIG
        args = self._args(body_file=str(tmp_path / "nope.md"))
        with pytest.raises(SystemExit) as exc:
            cmd_comment(args)
        assert exc.value.code != 0
        mock_add.assert_not_called()

    @patch("ticky._get_config")
    @patch("ticky.add_comment")
    def test_api_failure_exits_nonzero(self, mock_add, mock_get_config):
        mock_get_config.return_value = self.MOCK_CONFIG
        mock_add.side_effect = RuntimeError("HTTP 500: server error")
        args = self._args(body="hi")
        with pytest.raises(SystemExit) as exc:
            cmd_comment(args)
        assert exc.value.code != 0
