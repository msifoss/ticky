# Backlog — ticky

Last groomed: 2026-04-23

## Done

| # | Item | Size | Bolt |
|---|------|------|------|
| 1 | Core CLI: create work items from YAML/JSON | L | 1 |
| 2 | .md frontmatter ticket format with lifecycle metadata | L | 1 |
| 3 | GET and PATCH work item commands | M | 1 |
| 4 | Named profile support in .ticky.conf | M | 1 |
| 5 | `ticky sync` — pull ADO done-state into local .md files | M | 1 |
| 6 | PM docs bootstrap | S | 1 |
| 7 | CLAUDE.md, README.md, SECURITY.md | S | 2 |
| 8 | CHANGELOG | S | 2 |
| 9 | Add test suite (pytest) — 51 tests | M | 2 |
| 10 | `ticky submit` — full draft-to-ADO lifecycle | M | 2 |
| 11 | Batch create from directory of .md files | S | 2 |
| 12 | Tag v0.1.0 release | S | 2 |

## Executable

| # | Item | Size | Severity | Notes |
|---|------|------|----------|-------|
| 13 | **[BUG] `assigned_to` silently dropped on create (first ticket only gets assigned)** | M | Medium | When creating multiple tickets in sequence (or batch from a directory), only the first ticket lands with the `assigned_to` email applied — subsequent tickets in the same invocation (or subsequent invocations in quick succession) come back from ADO with `System.AssignedTo=null` despite `create` reporting success. Observed 2026-04-22 / 2026-04-23 on 4 ADO tickets: #8564 (assigned correctly), #8603, #8607, #8678 (all UNASSIGNED and required manual PATCH via ADO REST API to fix). Likely cause: identity-descriptor resolution succeeds once and caches, or the `assigned_to` email→identity lookup silently fails on retry and ADO drops the unknown-identity field without erroring. **Fix:** after POST, GET the created work item and verify `System.AssignedTo.uniqueName == requested_email`. If mismatch, retry with AAD descriptor format OR fail loudly with "identity not resolvable" error. Never silently succeed with a dropped field. **Regression test:** batch-create 3+ tickets with the same `assigned_to` and assert all three resolve to the correct identity. **Repro:** see `/Users/msichris/repos/callhero/docs/devops/20260423-1219-ado-permission-ticket-history-analysis.md` and ADO tickets #8603/#8607/#8678 in project `membersolutionsinc/DevOps`. |

## Blocked

_None_
