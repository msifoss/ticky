#!/usr/bin/env python3
"""ticky - CLI utility for injecting work items into Azure DevOps."""

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from config import list_profiles, load_config, validate_config

# ── Payload Builder ──────────────────────────────────────────────────────────


def build_payload(ticket: dict) -> list[dict]:
    """Convert a ticket dict into a JSON-Patch array for the ADO API.

    Skips internal keys (prefixed with '_') like _meta.
    """
    ops = [{"op": "add", "path": "/fields/System.Title", "value": ticket["title"]}]

    if "description" in ticket:
        ops.append(
            {"op": "add", "path": "/fields/System.Description", "value": ticket["description"]}
        )

    if "priority" in ticket:
        ops.append(
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.Common.Priority",
                "value": int(ticket["priority"]),
            }
        )

    if "tags" in ticket:
        ops.append({"op": "add", "path": "/fields/System.Tags", "value": ticket["tags"]})

    # Pass-through for arbitrary ADO fields
    for field_path, value in ticket.get("fields", {}).items():
        ops.append({"op": "add", "path": f"/fields/{field_path}", "value": value})

    return ops


# ── API Caller ───────────────────────────────────────────────────────────────


def create_work_item(config: dict, ticket: dict, verbose: bool = False) -> dict:
    """POST a work item to Azure DevOps. Returns the parsed JSON response."""
    work_item_type = ticket.get("type", config["work_item_type"])
    url = (
        f"https://dev.azure.com/{config['org']}/{config['project']}"
        f"/_apis/wit/workitems/${work_item_type}?api-version=7.0"
    )

    payload = build_payload(ticket)
    data = json.dumps(payload).encode("utf-8")
    auth = base64.b64encode(f":{config['pat']}".encode()).decode()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json-patch+json")
    req.add_header("Authorization", f"Basic {auth}")

    if verbose:
        print(f"  POST {url}", file=sys.stderr)
        print(f"  Payload: {json.dumps(payload, indent=2)}", file=sys.stderr)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if verbose:
            print(f"  Response {e.code}: {body}", file=sys.stderr)
        raise RuntimeError(f"HTTP {e.code}: {_extract_error(body, e.code)}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not connect to dev.azure.com: {e.reason}")


def get_work_item(config: dict, work_item_id: int, verbose: bool = False) -> dict:
    """GET a work item from Azure DevOps by ID. Returns the parsed JSON response."""
    url = (
        f"https://dev.azure.com/{config['org']}/{config['project']}"
        f"/_apis/wit/workitems/{work_item_id}?api-version=7.0&$expand=all"
    )

    auth = base64.b64encode(f":{config['pat']}".encode()).decode()

    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Basic {auth}")

    if verbose:
        print(f"  GET {url}", file=sys.stderr)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if verbose:
            print(f"  Response {e.code}: {body}", file=sys.stderr)
        raise RuntimeError(f"HTTP {e.code}: {_extract_error(body, e.code)}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not connect to dev.azure.com: {e.reason}")


def update_work_item(config: dict, work_item_id: int, patches: list[dict], verbose: bool = False) -> dict:
    """PATCH a work item in Azure DevOps. Returns the parsed JSON response."""
    url = (
        f"https://dev.azure.com/{config['org']}/{config['project']}"
        f"/_apis/wit/workitems/{work_item_id}?api-version=7.0"
    )

    data = json.dumps(patches).encode("utf-8")
    auth = base64.b64encode(f":{config['pat']}".encode()).decode()

    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("Content-Type", "application/json-patch+json")
    req.add_header("Authorization", f"Basic {auth}")

    if verbose:
        print(f"  PATCH {url}", file=sys.stderr)
        print(f"  Payload: {json.dumps(patches, indent=2)}", file=sys.stderr)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if verbose:
            print(f"  Response {e.code}: {body}", file=sys.stderr)
        raise RuntimeError(f"HTTP {e.code}: {_extract_error(body, e.code)}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not connect to dev.azure.com: {e.reason}")


def _extract_error(body: str, code: int) -> str:
    """Pull a human-readable message from ADO error responses."""
    if code == 401:
        return "Authentication failed. Check that your PAT is valid and has Work Items (Read & Write) scope."
    if code == 404:
        return "Project or work item type not found. Verify your org, project, and type settings."
    try:
        data = json.loads(body)
        return data.get("message", body)
    except (json.JSONDecodeError, KeyError):
        return body


# ── Markdown Ticket Parser ───────────────────────────────────────────────────

# Lifecycle fields stored in frontmatter but not sent to ADO
_META_KEYS = {"status", "ado_id", "assigned_to", "created", "submitted"}

# ADO states that mean a work item is finished
_ADO_DONE_STATES = {"Done", "Closed", "Resolved", "Removed"}


def parse_md_ticket(filepath: str) -> dict:
    """Parse an .md file with YAML frontmatter into a ticket dict.

    Frontmatter (between --- markers) provides ticket fields.
    Everything after the frontmatter becomes the description.
    Lifecycle fields (status, ado_id, etc.) are returned under a '_meta' key.
    """
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")

    # Split on frontmatter delimiters
    match = re.match(r"\A---\s*\n(.*?\n)---\s*\n(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"No YAML frontmatter found in {filepath}. Expected --- delimiters.")

    frontmatter_text, body = match.group(1), match.group(2)
    frontmatter = yaml.safe_load(frontmatter_text) or {}

    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter in {filepath} is not a YAML mapping")

    # Separate lifecycle metadata from ticket fields
    meta = {}
    ticket = {}
    for key, value in frontmatter.items():
        if key in _META_KEYS:
            meta[key] = value
        else:
            ticket[key] = value

    # Body becomes the description (strip leading/trailing whitespace)
    body = body.strip()
    if body:
        ticket["description"] = body

    if "title" not in ticket:
        raise ValueError(f"Ticket in {filepath} missing required field 'title'")

    ticket["_meta"] = meta
    return ticket


def _format_frontmatter_value(value) -> str:
    """Serialize a value for YAML frontmatter.

    Returns bare representation for simple strings/numbers, quoted if the
    value contains special YAML characters.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Quote if empty, or contains characters that could confuse YAML parsers
    if not s or any(ch in s for ch in ":#{}[]|>&*!?,\n"):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def update_md_frontmatter(filepath: str, updates: dict) -> None:
    """Update specific frontmatter keys in an .md file, preserving everything else.

    Replaces only the keys present in `updates`. Preserves all other
    frontmatter lines and the body byte-for-byte. Does NOT use yaml.dump
    to avoid key reordering, quote-style changes, and reformatting.
    """
    path = Path(filepath)
    text = path.read_text(encoding="utf-8")

    match = re.match(r"\A---\s*\n(.*?\n)---\s*\n(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"No YAML frontmatter found in {filepath}")

    frontmatter_text, body = match.group(1), match.group(2)

    # Replace matching key lines; track which updates were applied
    applied = set()
    new_lines = []
    for line in frontmatter_text.splitlines(keepends=True):
        stripped = line.lstrip()
        matched_key = None
        for key in updates:
            if stripped.startswith(f"{key}:"):
                matched_key = key
                break
        if matched_key is not None:
            indent = line[: len(line) - len(stripped)]
            new_lines.append(f"{indent}{matched_key}: {_format_frontmatter_value(updates[matched_key])}\n")
            applied.add(matched_key)
        else:
            new_lines.append(line)

    # Append any keys that weren't already in the frontmatter
    for key, value in updates.items():
        if key not in applied:
            new_lines.append(f"{key}: {_format_frontmatter_value(value)}\n")

    new_text = "---\n" + "".join(new_lines) + "---\n" + body
    path.write_text(new_text, encoding="utf-8")


# ── File Loader ──────────────────────────────────────────────────────────────


def load_tickets(filepath: str) -> list[dict]:
    """Read a YAML or JSON file and return a normalized list of ticket dicts."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Markdown files with frontmatter get their own parser
    if path.suffix == ".md":
        ticket = parse_md_ticket(filepath)
        return [ticket]

    text = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif path.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix} (use .yaml, .yml, .json, or .md)")

    # Normalize to list of tickets
    if isinstance(data, dict):
        if "tickets" in data and isinstance(data["tickets"], list):
            tickets = data["tickets"]
        else:
            tickets = [data]
    elif isinstance(data, list):
        tickets = data
    else:
        raise ValueError(f"Unexpected data format in {filepath}")

    # Validate
    for i, ticket in enumerate(tickets):
        if not isinstance(ticket, dict):
            raise ValueError(f"Ticket at index {i} is not a dict")
        if "title" not in ticket:
            raise ValueError(f"Ticket at index {i} missing required field 'title'")

    return tickets


# ── Subcommands ──────────────────────────────────────────────────────────────


def cmd_create(args):
    """Create work item(s) from a ticket file or directory."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    target = Path(args.file)
    if target.is_dir():
        files = sorted(target.glob("*.md"))
        if not files:
            print(f"No .md files found in {target}")
            return
        all_tickets = []
        for f in files:
            try:
                all_tickets.extend(load_tickets(str(f)))
            except (FileNotFoundError, ValueError) as e:
                print(f"Warning: skipping {f.name}: {e}", file=sys.stderr)
        tickets = all_tickets
    else:
        try:
            tickets = load_tickets(args.file)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"Processing {len(tickets)} ticket(s)...\n")

    created = 0
    failed = 0

    for i, ticket in enumerate(tickets):
        title = ticket["title"]
        truncated = title[:60] + "..." if len(title) > 60 else title

        if args.dry_run:
            payload = build_payload(ticket)
            wi_type = ticket.get("type", config["work_item_type"])
            print(f"[DRY RUN] #{i + 1}  {truncated}")
            print(f"          Type: {wi_type}")
            print(f"          Payload: {json.dumps(payload, indent=2)}")
            print()
            created += 1
            continue

        try:
            result = create_work_item(config, ticket, verbose=args.verbose)
            wi_id = result.get("id", "?")
            wi_url = result.get("_links", {}).get("html", {}).get("href", "")
            print(f"[OK]   #{wi_id}  {truncated}")
            if wi_url:
                print(f"       {wi_url}")
            created += 1
        except RuntimeError as e:
            print(f"[FAIL] {truncated}")
            print(f"       {e}")
            failed += 1

        print()

    # Summary for batch
    if len(tickets) > 1:
        print("--- Results ---")
        print(f"Created: {created}")
        if failed:
            print(f"Failed:  {failed}")

    if failed:
        sys.exit(1)


def cmd_validate(args):
    """Validate a ticket file without hitting the API."""
    try:
        tickets = load_tickets(args.file)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(tickets)} ticket(s) from {args.file}\n")

    for i, ticket in enumerate(tickets):
        title = ticket["title"]
        wi_type = ticket.get("type", "default")
        priority = ticket.get("priority", "-")
        tags = ticket.get("tags", "-")
        has_desc = "yes" if "description" in ticket else "no"
        extra_fields = len(ticket.get("fields", {}))

        print(f"  Ticket {i + 1}:")
        print(f"    Title:       {title}")
        print(f"    Type:        {wi_type}")
        print(f"    Priority:    {priority}")
        print(f"    Tags:        {tags}")
        print(f"    Description: {has_desc}")
        if extra_fields:
            print(f"    Extra fields: {extra_fields}")
        print()

    print("Validation passed.")


def cmd_init(args):
    """Generate template config and example ticket files."""
    conf_path = Path.home() / ".ticky.conf"
    if conf_path.exists():
        print(f"Config already exists: {conf_path}")
    else:
        conf_path.write_text(
            "# Ticky configuration - profiles for Azure DevOps targets\n"
            "# [default] is used when no --profile is specified.\n"
            "# Named profiles inherit from [default] and override specific values.\n"
            "#\n"
            "# Usage:\n"
            "#   ticky create ticket.yaml              (uses [default])\n"
            "#   ticky create ticket.yaml -P devops    (uses [devops] profile)\n"
            "#   ticky profiles                        (list all profiles)\n"
            "\n"
            "[default]\n"
            "pat = YOUR_PERSONAL_ACCESS_TOKEN\n"
            "org = membersolutionsinc\n"
            "project = DevOps\n"
            "work_item_type = Issue\n"
            "\n"
            "# Example: a second project in the same org\n"
            "# [engineering]\n"
            "# project = Engineering\n"
            "# work_item_type = Task\n"
            "\n"
            "# Example: a different org entirely (needs its own PAT)\n"
            "# [other-org]\n"
            "# pat = DIFFERENT_PAT_HERE\n"
            "# org = otherorgname\n"
            "# project = SomeProject\n",
            encoding="utf-8",
        )
        print(f"Created config: {conf_path}")
        print("  Edit this file to add your PAT and configure profiles.\n")

    example_path = Path.cwd() / "example-ticket.yaml"
    if example_path.exists():
        print(f"Example already exists: {example_path}")
    else:
        example_path.write_text(
            'title: "Example: My work item title"\n'
            "description: |\n"
            "  <h2>Description</h2>\n"
            "  <p>Describe the work item here. HTML is supported.</p>\n"
            "priority: 2\n"
            'tags: "Tag1; Tag2"\n',
            encoding="utf-8",
        )
        print(f"Created example ticket: {example_path}")
        print("  Edit this file and run: ticky create example-ticket.yaml\n")


# ── Helpers ──────────────────────────────────────────────────────────────────


def cmd_profiles(args):
    """List all configured profiles."""
    profiles = list_profiles()
    if not profiles:
        print("No profiles found. Run 'ticky init' to create ~/.ticky.conf")
        return

    print("Configured profiles:\n")
    for p in profiles:
        name = p["name"]
        org = p["org"] or "(inherit)"
        project = p["project"] or "(inherit)"
        wi_type = p["work_item_type"] or "(inherit)"
        pat = "yes" if p["has_pat"] else "no"
        print(f"  [{name}]")
        print(f"    org:    {org}")
        print(f"    project: {project}")
        print(f"    type:    {wi_type}")
        print(f"    pat:     {pat}")
        print(f"    source:  {p['source']}")
        print()


def cmd_get(args):
    """Get a work item from Azure DevOps by ID."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = get_work_item(config, args.id, verbose=args.verbose)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    fields = result.get("fields", {})
    wi_id = result.get("id", "?")
    title = fields.get("System.Title", "(no title)")
    state = fields.get("System.State", "?")
    assigned = fields.get("System.AssignedTo", {})
    assigned_name = assigned.get("displayName", "Unassigned") if isinstance(assigned, dict) else str(assigned) if assigned else "Unassigned"
    priority = fields.get("Microsoft.VSTS.Common.Priority", "-")
    tags = fields.get("System.Tags", "-")
    wi_type = fields.get("System.WorkItemType", "?")
    created = fields.get("System.CreatedDate", "?")
    url = result.get("_links", {}).get("html", {}).get("href", "")

    print(f"  ID:         #{wi_id}")
    print(f"  Title:      {title}")
    print(f"  Type:       {wi_type}")
    print(f"  State:      {state}")
    print(f"  Assigned:   {assigned_name}")
    print(f"  Priority:   {priority}")
    print(f"  Tags:       {tags}")
    print(f"  Created:    {created}")
    if url:
        print(f"  URL:        {url}")


def cmd_update(args):
    """Update a work item in Azure DevOps."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    patches = []
    if args.state:
        patches.append({"op": "add", "path": "/fields/System.State", "value": args.state})
    if args.assign:
        patches.append({"op": "add", "path": "/fields/System.AssignedTo", "value": args.assign})
    if args.title:
        patches.append({"op": "add", "path": "/fields/System.Title", "value": args.title})
    if args.priority is not None:
        patches.append({"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": int(args.priority)})
    if args.tags:
        patches.append({"op": "add", "path": "/fields/System.Tags", "value": args.tags})

    if not patches:
        print("Error: No updates specified. Use --state, --assign, --title, --priority, or --tags.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"[DRY RUN] Update work item #{args.id}")
        print(f"  Patches: {json.dumps(patches, indent=2)}")
        return

    try:
        result = update_work_item(config, args.id, patches, verbose=args.verbose)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    wi_id = result.get("id", "?")
    fields = result.get("fields", {})
    state = fields.get("System.State", "?")
    title = fields.get("System.Title", "?")
    print(f"[OK] Updated #{wi_id}: {title}")
    print(f"     State: {state}")


def sync_ticket(filepath: str, config: dict, dry_run: bool = False, verbose: bool = False) -> str | None:
    """Sync a single .md ticket's status with Azure DevOps.

    Returns a status string: "updated", "current", "skipped", "error: ...",
    or None if the file is not an .md file.
    """
    path = Path(filepath)
    if path.suffix != ".md":
        return None

    try:
        ticket = parse_md_ticket(filepath)
    except ValueError as e:
        return f"error: {e}"

    meta = ticket.get("_meta", {})
    status = meta.get("status", "")
    ado_id = meta.get("ado_id")

    # Only sync tickets that have been submitted
    if status != "submitted":
        return "skipped"

    if not ado_id:
        return "skipped"

    try:
        wi_id = int(ado_id)
    except (ValueError, TypeError):
        return f"error: invalid ado_id '{ado_id}'"

    try:
        result = get_work_item(config, wi_id, verbose=verbose)
    except RuntimeError as e:
        return f"error: {e}"

    ado_state = result.get("fields", {}).get("System.State", "")

    if ado_state not in _ADO_DONE_STATES:
        if verbose:
            print(f"  {path.name}: ADO state is '{ado_state}', not done", file=sys.stderr)
        return "current"

    if dry_run:
        print(f"  [DRY RUN] {path.name}: would update status → done (ADO state: {ado_state})")
        return "updated"

    try:
        update_md_frontmatter(filepath, {"status": "done"})
    except (ValueError, OSError) as e:
        return f"error: could not write {path.name}: {e}"

    return "updated"


def cmd_sync(args):
    """Sync local .md ticket statuses with Azure DevOps."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    target = Path(args.path)
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.glob("*.md"))
        if not files:
            print(f"No .md files found in {target}")
            return
    else:
        print(f"Error: {args.path} is not a file or directory", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run
    verbose = args.verbose

    if dry_run:
        print("[DRY RUN] No files will be modified.\n")

    counts = {"updated": 0, "current": 0, "skipped": 0, "errors": 0}

    for f in files:
        result = sync_ticket(str(f), config, dry_run=dry_run, verbose=verbose)
        if result is None:
            continue
        elif result == "updated":
            if not dry_run:
                print(f"  [UPDATED] {f.name}: status → done")
            counts["updated"] += 1
        elif result == "current":
            if verbose:
                print(f"  [CURRENT] {f.name}: still open in ADO")
            counts["current"] += 1
        elif result == "skipped":
            if verbose:
                print(f"  [SKIPPED] {f.name}")
            counts["skipped"] += 1
        elif result.startswith("error:"):
            print(f"  [ERROR]   {f.name}: {result[7:]}")
            counts["errors"] += 1

    print(f"\n--- Sync Summary ---")
    print(f"Updated: {counts['updated']}")
    print(f"Current: {counts['current']}")
    print(f"Skipped: {counts['skipped']}")
    if counts["errors"]:
        print(f"Errors:  {counts['errors']}")


def cmd_submit(args):
    """Submit a draft .md ticket to ADO and update local file."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    filepath = Path(args.file)
    if not filepath.is_file():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if filepath.suffix != ".md":
        print(f"Error: Submit requires an .md file, got {filepath.suffix}", file=sys.stderr)
        sys.exit(1)

    try:
        ticket = parse_md_ticket(str(filepath))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    meta = ticket.get("_meta", {})
    if meta.get("status") != "draft":
        print(f"Error: File status is '{meta.get('status', 'unknown')}', expected 'draft'", file=sys.stderr)
        sys.exit(1)

    title = ticket["title"]
    truncated = title[:60] + "..." if len(title) > 60 else title

    if args.dry_run:
        payload = build_payload(ticket)
        wi_type = ticket.get("type", config["work_item_type"])
        print(f"[DRY RUN] Submit: {truncated}")
        print(f"          Type: {wi_type}")
        print(f"          Payload: {json.dumps(payload, indent=2)}")
        return

    try:
        result = create_work_item(config, ticket, verbose=args.verbose)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    wi_id = result.get("id", "?")
    wi_url = result.get("_links", {}).get("html", {}).get("href", "")

    # Update frontmatter
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    updates = {"status": "submitted", "ado_id": wi_id, "submitted": now}

    if args.assign:
        try:
            update_work_item(config, wi_id, [
                {"op": "add", "path": "/fields/System.AssignedTo", "value": args.assign}
            ], verbose=args.verbose)
            updates["assigned_to"] = args.assign
        except RuntimeError as e:
            print(f"Warning: Created #{wi_id} but assignment failed: {e}", file=sys.stderr)

    try:
        update_md_frontmatter(str(filepath), updates)
    except (ValueError, OSError) as e:
        print(f"Warning: Created #{wi_id} but could not update file: {e}", file=sys.stderr)

    # Rename file: -draft.md → -submitted.md
    new_name = filepath.name.replace("-draft.md", "-submitted.md")
    if new_name != filepath.name:
        new_path = filepath.parent / new_name
        filepath.rename(new_path)
        print(f"[OK] #{wi_id}  {truncated}")
        print(f"     Renamed: {new_name}")
    else:
        print(f"[OK] #{wi_id}  {truncated}")

    if wi_url:
        print(f"     {wi_url}")


def _get_config(args) -> dict:
    """Build merged config from all sources."""
    cli_overrides = {
        "pat": getattr(args, "pat", None),
        "org": getattr(args, "org", None),
        "project": getattr(args, "project", None),
        "work_item_type": getattr(args, "type", None),
    }
    profile = getattr(args, "profile", None)
    return load_config(cli_overrides, profile=profile)


# ── CLI Setup ────────────────────────────────────────────────────────────────


def main():
    # Parent parser with shared global flags (inherited by all subcommands)
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--org", "-o", help="Azure DevOps organization")
    parent.add_argument("--project", "-p", help="ADO project name")
    parent.add_argument("--type", "-t", help="Default work item type (Issue, Task, Bug, etc.)")
    parent.add_argument("--pat", help="Personal access token (prefer config file or env var)")
    parent.add_argument("--config", "-c", help="Path to config file")
    parent.add_argument("--profile", "-P", help="Named profile from .ticky.conf (e.g. devops, engineering)")
    parent.add_argument("--verbose", "-v", action="store_true", help="Print request details")

    parser = argparse.ArgumentParser(
        prog="ticky",
        description="CLI utility for injecting work items into Azure DevOps",
        parents=[parent],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser(
        "create", parents=[parent], help="Create work item(s) from a file or directory"
    )
    p_create.add_argument("file", help="Path to ticket file or directory of .md files")
    p_create.add_argument(
        "--dry-run", "-n", action="store_true", help="Show payload without creating"
    )
    p_create.set_defaults(func=cmd_create)

    # validate
    p_validate = subparsers.add_parser(
        "validate", parents=[parent], help="Validate a ticket file (no API call)"
    )
    p_validate.add_argument("file", help="Path to ticket YAML/JSON/MD file")
    p_validate.set_defaults(func=cmd_validate)

    # init
    p_init = subparsers.add_parser(
        "init", parents=[parent], help="Generate template config and example ticket"
    )
    p_init.set_defaults(func=cmd_init)

    # profiles
    p_profiles = subparsers.add_parser(
        "profiles", parents=[parent], help="List all configured profiles"
    )
    p_profiles.set_defaults(func=cmd_profiles)

    # get
    p_get = subparsers.add_parser(
        "get", parents=[parent], help="Get a work item from Azure DevOps by ID"
    )
    p_get.add_argument("id", type=int, help="Work item ID")
    p_get.add_argument("--json", action="store_true", help="Output raw JSON response")
    p_get.set_defaults(func=cmd_get)

    # update
    p_update = subparsers.add_parser(
        "update", parents=[parent], help="Update a work item in Azure DevOps"
    )
    p_update.add_argument("id", type=int, help="Work item ID")
    p_update.add_argument("--state", help="Set work item state (e.g. New, Active, Closed)")
    p_update.add_argument("--assign", help="Assign to a person (display name)")
    p_update.add_argument("--title", help="Update the title")
    p_update.add_argument("--priority", type=int, help="Set priority (1-4)")
    p_update.add_argument("--tags", help="Set tags (semicolon-separated)")
    p_update.add_argument(
        "--dry-run", "-n", action="store_true", help="Show patches without applying"
    )
    p_update.set_defaults(func=cmd_update)

    # sync
    p_sync = subparsers.add_parser(
        "sync", parents=[parent], help="Sync local .md ticket statuses with Azure DevOps"
    )
    p_sync.add_argument("path", help="Path to .md file or directory of .md files")
    p_sync.add_argument(
        "--dry-run", "-n", action="store_true", help="Show what would change without modifying files"
    )
    p_sync.set_defaults(func=cmd_sync)

    # submit
    p_submit = subparsers.add_parser(
        "submit", parents=[parent], help="Submit a draft .md ticket to Azure DevOps"
    )
    p_submit.add_argument("file", help="Path to draft .md ticket file")
    p_submit.add_argument("--assign", help="Assign to a person after creation")
    p_submit.add_argument(
        "--dry-run", "-n", action="store_true", help="Show payload without submitting"
    )
    p_submit.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
