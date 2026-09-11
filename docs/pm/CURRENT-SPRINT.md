# Current Sprint — Bolt 3: Ticket Quality Hardening (Prompt Layer)

**Opened:** 2026-05-27
**Status:** Planning → ready to execute
**Driver:** CallHero ticket-quality audit (2026-05-27), 18 findings on ADO #10855 + #10921
**Related:** Bolt 4 (deferred ~2 weeks) ships the code/enforcement layer

## Goal

Convert ticky's ticket-prompt template from a specification format into a
test-contract format. Every ticket ticky helps generate should, by default,
ship with: a falsification step (catches wrong diagnosis), a verification
command both parties can run, a rollback, a definition of done, an honest
wall-time estimate, and a `ticket_class` declaration that drives downstream
prompt branching + (later) lint + tag mapping.

**This Bolt is prompt-only — zero code changes.** Layer-2 enforcement
(`ticky validate`, `ticky lint`, `ticky verify`, `ticky sync` closure rules)
ships in Bolt 4 after ~2 weeks of measuring Layer-1 impact.

## Why now

The CallHero audit estimated ~12.5 engineer-hours burned on two tickets that
should have been ~10 min of active work — fully-loaded ~$1,600-$2,000 for
5 IAM actions and 2 LF permissions. Three tickets in eight weeks (#10349,
#10855, #10921) show the same protocol failure shape. The single highest-
ROI fix is one template change. Template fix is zero-code, ships today;
savings start with the first ticket filed after it lands.

## Why two bolts (per /staff panel ruling)

Prompt is markdown; code is forever. Layer 1 (prompt) is zero-risk — no
migration, no test regression, no version bump. Ship it, measure for 2
weeks, then decide whether Layer 2 (code/enforcement) is still worth its
~150 LOC + new subcommands. The prompt changes alone may fix 60% of the
burn pattern.

## Success criteria (Bolt 3)

- `templates/ticket-prompt.md` requires `ticket_class` frontmatter field
  (enum: general / cross-account-iam / cross-account-data-lake /
  sso-permission-set / cfn-rotation-risk; default general).
- Prompt branches section generation on class.
- Falsification section (NEW, ranked first for cross-account classes) is
  required before Verification — Rob's epistemic distinction: falsification
  catches wrong diagnoses; verification only proves the change was applied.
- Verification, Rollback, Definition of Done, Confidence-in-Diagnosis-with-
  evidence-criteria, Effort+Wall-Time split sections all added.
- The "Two Options" anchor framing is replaced by "Recommended Path +
  Constraints + Acceptable Alternatives."
- `templates/ticket-prompt.md` is referenced from `CLAUDE.md` and `README.md`
  so first-time users land on the contract immediately.
- One worked example in `examples/` demonstrates the full new contract on
  a cross-account-iam-class ticket (mirrors CallHero #10921 shape).

## Items in scope (P0/P1 — see BACKLOG.md #14-#19)

| Priority | Items |
|----------|-------|
| P0 (must) | #14 (ticket_class field), #15 (Falsification + Verification), #16 (Recommended Path framing) |
| P1 (should) | #17 (Rollback + DoD), #18 (Effort + Mitigation + Confidence), #19 (example + README/CLAUDE/CHANGELOG + tag v0.2.0) |

## Out of scope (deferred to Bolt 4)

- `ticky validate` enforcement of `ticket_class` field
- `ticky lint` subcommand (warns on missing class-appropriate sections)
- `ticky submit` pre-flight (file-path existence; title SHA/path warning)
- `ticket_class` → ADO tag auto-mapping at submit time
- `ticky verify <id>` + `ticky sync` two-signature closure enforcement
  (the load-bearing change per /staff panel; ~80 LOC, shipped behind
  `[enforce_closure]` opt-in flag)

## Out of scope (permanently — per /staff ruling)

- `ticky verify-snippet` subcommand to generate AWS CLI boilerplate —
  ticky must not own AWS CLI invocation syntax; AWS API drift would eat us
- YAML verification schema rendered into HTML — same reason
- Commit-SHA-against-main validation — out of scope for a ticket tool
- Sub-templates per class — one template, prompt-side branching is enough
- AWS Support workflow / two-signature enforcement at ADO level — those
  belong in the requesting project (e.g., CallHero), not in ticky
- Retroactive re-tagging of historical ADO tickets — manual ops

## Dependencies

```
#14 (ticket_class field) ──► #15 (Falsification + Verification)
                          └─► #16 (Recommended Path framing)
                          └─► #17 (Rollback + DoD)
                          └─► #18 (Effort + Mitigation + Confidence)

All ──► #19 (example + README/CLAUDE/CHANGELOG + tag v0.2.0)
```

Recommended landing order: #14 → #15 → #16 → #17 → #18 → #19.
All six items edit a single file (`templates/ticket-prompt.md`) + the close-
out item adds an example + docs. Can land in 2-3 commits total.

## Effort

- P0 (#14, #15, #16): S + M + M ≈ ~half day
- P1 (#17, #18, #19): S + S + M ≈ ~half day

**Total Bolt 3 estimate: ~1 day of focused work.**

## Source documents

- `/Users/msichris/repos/callhero/docs/reviews/20260527-1930-ticket-quality-twelve-persona-review.txt`
- `/Users/msichris/repos/callhero/docs/key_findings/20260527-1930-ticket-instructions-correctness-staff-panel.md`
- `/Users/msichris/repos/ticky/docs/captains_log/caplog-20260527-2030-bolt3-planned.txt`

## Forward look — Bolt 4 (deferred ~2 weeks)

Code/enforcement layer per /staff ruling Phase 5 Steps 2-5:

- **#20** `ticky validate` enforces `ticket_class` is present + valid (~15 LOC, ~3 tests)
- **#21** `ticky submit` pre-flight: file paths must exist on disk; warn if title contains a path or commit SHA (~30 LOC, ~5 tests)
- **#22** `ticket_class` → ADO tag auto-map at submit time (~20 LOC, ~3 tests)
- **#23** `ticky lint` subcommand: walks .md, warns on missing class-appropriate `## Heading` markers; exits 0 regardless (~50 LOC, ~5 tests)
- **#24** `ticky verify <id> --role {requester|resolver} --output <file-or-paste>` writes append-only `_meta.verifications:` array; `ticky sync` refuses `status: done` without both roles' signatures unless `--force`; 7-day auto-promote to `done-unverified` (~80 LOC, ~10 tests; shipped behind `[enforce_closure]` opt-in)

Open Bolt 4 only after ~2 weeks of Bolt 3 prompt-evolution in production
and a metric check on whether the prompt-only changes moved the needle.
