# Security — ticky

## Overview

ticky is a CLI tool that authenticates to Azure DevOps using Personal Access Tokens (PATs). It handles sensitive credentials and makes HTTP requests to external APIs.

## Threat Model

| Threat | Mitigation | Status |
|--------|-----------|--------|
| PAT exposure in source control | `.gitignore` excludes `.ticky.conf` and `tickypat.txt`; PAT never logged in normal output | Mitigated |
| PAT exposure in process list | PAT passed via `--pat` flag is visible in `ps` output; prefer config file or env var | Documented |
| PAT in verbose output | Verbose mode (`-v`) logs URLs but not auth headers | Mitigated |
| Command injection via ticket fields | Ticket data sent as JSON payload, not shell-interpolated | Mitigated |
| HTML injection in descriptions | Ticket descriptions are HTML by design (ADO renders HTML); no sanitization needed for this use case | Accepted |
| Man-in-the-middle | All API calls use HTTPS to `dev.azure.com` | Mitigated |
| Arbitrary file write via sync | `update_md_frontmatter()` only writes to files explicitly passed by the user; validates frontmatter structure before writing | Mitigated |

## Credential Handling

- **Config file:** `~/.ticky.conf` stores PAT in `[default]` section. File should be `chmod 600`.
- **Environment variable:** `TICKY_PAT` — preferred for CI/CD and automation.
- **CLI flag:** `--pat` — visible in process list; use only for one-off commands.
- **PAT file:** `tickypat.txt` — used by skill automation; excluded from git via `.gitignore`.

## Recommendations

1. Use environment variables or config files for PAT storage, not CLI flags
2. Set `chmod 600 ~/.ticky.conf` to restrict access
3. Use PATs with minimal scope: **Work Items (Read & Write)** only
4. Rotate PATs periodically (Azure DevOps supports expiration dates)

## Audit Log

| Date | Event | Findings |
|------|-------|----------|
| 2026-03-04 | Initial security baseline | No critical issues; PAT handling follows standard practices |
