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
    """Create work item(s) from a ticket file."""
    config = _get_config(args)
    errors = validate_config(config)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

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
        "create", parents=[parent], help="Create work item(s) from a YAML/JSON/MD file"
    )
    p_create.add_argument("file", help="Path to ticket YAML/JSON/MD file")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
