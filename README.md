# ticky

CLI utility for managing Azure DevOps work items. Create, read, update, and sync work items from the command line using local `.md` ticket files with YAML frontmatter.

## Install

```bash
pip install -e .
```

Requires Python 3.10+ and PyYAML.

## Setup

```bash
ticky init
```

This creates `~/.ticky.conf` with your ADO configuration:

```ini
[default]
pat = YOUR_PERSONAL_ACCESS_TOKEN
org = your-org
project = YourProject
work_item_type = Issue
```

## Usage

### Create a work item

```bash
# From YAML, JSON, or Markdown
ticky create ticket.yaml
ticky create ticket.md

# Dry run (show payload without creating)
ticky create ticket.yaml --dry-run
```

### Get a work item

```bash
ticky get 5139
ticky get 5139 --json
```

### Update a work item

```bash
ticky update 5139 --state Active
ticky update 5139 --assign "Jane Doe" --priority 1 --tags "Bug; P1"
```

### Sync local tickets with ADO

Pull ADO state back into local `.md` files. Updates `status: submitted` to `status: done` when the ADO work item is Done/Closed/Resolved/Removed.

```bash
ticky sync docs/tickets/          # sync all .md files in directory
ticky sync docs/tickets/my-ticket.md  # sync a single file
ticky sync docs/tickets/ --dry-run    # preview changes
```

### Validate a ticket file

```bash
ticky validate ticket.yaml
```

### Named profiles

Target different ADO orgs/projects:

```ini
# ~/.ticky.conf
[default]
pat = TOKEN_A
org = my-org
project = ProjectA

[engineering]
project = Engineering
work_item_type = Task
```

```bash
ticky create ticket.yaml --profile engineering
ticky profiles  # list all configured profiles
```

## Ticket Markdown Format

```markdown
---
title: "My work item"
type: Issue
priority: 2
tags: "Tag1; Tag2"
status: draft
ado_id: null
assigned_to: null
created: 2026-03-01T14:30:00
submitted: null
---

Description body here (HTML supported).
```

## Configuration Resolution

Settings are merged in order (later wins):

1. `~/.ticky.conf` `[default]` section
2. `~/.ticky.conf` `[named-profile]` section
3. `./.ticky.conf` `[default]` section
4. `./.ticky.conf` `[named-profile]` section
5. Environment variables (`TICKY_PAT`, `TICKY_ORG`, `TICKY_PROJECT`, `TICKY_WORK_ITEM_TYPE`)
6. CLI flags (`--pat`, `--org`, `--project`, `--type`)
