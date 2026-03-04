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
