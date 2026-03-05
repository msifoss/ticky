# ticky — ADO Work Item CLI

CLI utility for managing Azure DevOps work items. Creates, reads, updates, and syncs work items using the ADO REST API. Manages local `.md` ticket files with YAML frontmatter as the source of truth for ticket lifecycle.

## Architecture

```
ticky.py      (892 lines)  — CLI entry point, all subcommands, API callers, .md parser/writer
config.py     (125 lines)  — Config loading (INI files, env vars, CLI flags, profiles)
tests/        (51 tests)   — pytest suite for core functions (build_payload, parse_md, sync, config)
templates/ticket-prompt.md — Prompt template for generating ticket HTML bodies
```

**No external dependencies except PyYAML.** All HTTP via `urllib.request` (no requests library). Python 3.10+.

## Key Concepts

- **Ticket lifecycle:** `draft` → `submitted` → `done` (tracked in frontmatter `status` field)
- **Frontmatter metadata:** `status`, `ado_id`, `assigned_to`, `created`, `submitted` — stored in `.md` files, not sent to ADO
- **Config resolution:** `~/.ticky.conf` → `./.ticky.conf` → env vars → CLI flags (later wins)
- **Named profiles:** `[default]`, `[engineering]`, etc. in `.ticky.conf` — selected via `--profile`/`-P`

## Commands

| Command | Purpose |
|---------|---------|
| `create <file\|dir>` | Create work item(s) from file or directory |
| `submit <file>` | Submit a draft .md to ADO, update frontmatter, rename file |
| `validate <file>` | Dry-validate ticket file |
| `get <id>` | Fetch work item by ID |
| `update <id>` | Patch work item fields |
| `sync <path>` | Pull ADO state into local `.md` frontmatter |
| `init` | Scaffold `~/.ticky.conf` + example ticket |
| `profiles` | List configured profiles |

## Conventions

- All API calls use `urllib.request` with Basic auth (PAT)
- Error handling: `RuntimeError` for API errors, `ValueError` for parse errors
- CLI uses `argparse` with parent parser for shared flags
- `_META_KEYS` separates lifecycle fields from ADO-bound fields
- `update_md_frontmatter()` does line-by-line replacement (no `yaml.dump`) to preserve formatting

## Current Status

- **Version:** 0.1.0
- **Tests:** 51 (pytest)
- **Last updated:** 2026-03-04
