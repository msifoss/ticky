# Changelog — ticky

All notable changes to this project.

## [Unreleased]

### Added
- `ticky submit` command — submit a draft `.md` ticket to ADO, update frontmatter with `ado_id`/`status: submitted`, rename file from `-draft.md` to `-submitted.md`. Supports `--assign` and `--dry-run`.
- Batch create from directory — `ticky create docs/tickets/` globs `*.md` and creates each.
- Test suite — 51 pytest tests covering `build_payload`, `parse_md_ticket`, `update_md_frontmatter`, `sync_ticket`, and config loading.
- `CLAUDE.md` — project identity and architecture reference.
- `README.md` — usage documentation.
- `SECURITY.md` — baseline security doc covering PAT handling and threat model.

## [0.1.0] — 2026-03-04

### Added
- `ticky sync` command — pulls ADO work item state back into local .md frontmatter, updating `status: submitted` to `status: done` when ADO state is Done/Closed/Resolved/Removed. Supports single file or directory, `--dry-run`, `--verbose`.
- Named profile support in `.ticky.conf` — use `--profile`/`-P` to target different ADO orgs/projects.
- `ticky get <id>` — fetch and display a work item by ID (with `--json` for raw output).
- `ticky update <id>` — patch work item fields (state, assignee, title, priority, tags).
- `.md` ticket format with YAML frontmatter — lifecycle metadata (`status`, `ado_id`, `submitted`) tracked locally.
- `ticky create` — create work items from YAML, JSON, or .md files.
- `ticky validate` — dry-validate ticket files without hitting the API.
- `ticky init` — scaffold `~/.ticky.conf` and example ticket.
- `ticky profiles` — list all configured profiles.
