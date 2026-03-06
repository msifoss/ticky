# Sprint Log — ticky

Archive of completed Bolts.

---

## Bolt 1 — Core CLI with Bidirectional Sync

**Goal:** Build a complete ADO work item CLI with bidirectional sync.
**Opened:** 2026-03-03
**Closed:** 2026-03-04
**Status:** Completed

### Completed Items

| # | Item | Size |
|---|------|------|
| 1 | Initial CLI scaffold (create, validate, init) | L |
| 2 | .md ticket parsing, GET/PATCH commands, profiles | L |
| 3 | Named profile support, improved ticket prompt | M |
| 4 | `ticky sync` — pull ADO state into local .md | M |
| 5 | PM docs bootstrap, archive redundant tickets | M |

### Metrics

- Commits: 5
- Tests: 0
- Files changed: 3 core (ticky.py, config.py, templates/ticket-prompt.md)

### Retro

**What went well:** Rapid buildout from zero to a fully functional bidirectional ADO CLI in one bolt. The sync command immediately proved useful — synced 16 callhero tickets from `submitted` to `done` on first run. Clean operation across 6 repos archived 36 redundant files.

**What to improve:** No tests written during the build phase. CLAUDE.md and README were deferred. Should establish docs and tests alongside code from the start.

**Carry-forward:** Test suite, `ticky submit` lifecycle, batch create, docs/README.

---

## Bolt 2 — Harden with Tests, Docs & Hygiene

**Goal:** Harden ticky with tests, docs, and project hygiene.
**Opened:** 2026-03-04
**Closed:** 2026-03-05
**Status:** Completed

### Completed Items

| # | Item | Size |
|---|------|------|
| 1 | Create CLAUDE.md | S |
| 2 | Create README.md | S |
| 3 | Create SECURITY.md | S |
| 4 | Close Bolt 1, archive to SPRINT-LOG | S |
| 5 | Add test suite (pytest) — 51 tests | M |
| 6 | `ticky submit` — full draft-to-ADO lifecycle | M |
| 7 | Batch create from directory | S |

### Metrics

- Commits: 2 (docs + code)
- Tests: 51 (from 0)
- Tag: v0.1.0

### Retro

**What went well:** All Bolt 1 carry-forward items resolved. Test suite covers all core functions (build_payload, parse_md, update_frontmatter, sync, config). Submit command completes the full draft-to-ADO lifecycle. Motherhen health check improved from 0 PASS / 3 FAIL to 3 PASS / 3 WARN.

**What to improve:** BACKLOG items weren't moved to Done as they were completed — caused drift caught by motherhen. Should update backlog in real-time.

**Carry-forward:** AI-DLC foundation docs (2/14), release v0.2.0 for unreleased changes.
