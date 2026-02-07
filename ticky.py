#!/usr/bin/env python3
"""ticky - CLI utility for injecting work items into Azure DevOps."""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from config import load_config, validate_config

# ── Payload Builder ──────────────────────────────────────────────────────────


def build_payload(ticket: dict) -> list[dict]:
    """Convert a ticket dict into a JSON-Patch array for the ADO API."""
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


# ── File Loader ──────────────────────────────────────────────────────────────


def load_tickets(filepath: str) -> list[dict]:
    """Read a YAML or JSON file and return a normalized list of ticket dicts."""
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {filepath}")

    text = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif path.suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix} (use .yaml, .yml, or .json)")

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
            "[ado]\n"
            "pat = YOUR_PERSONAL_ACCESS_TOKEN\n"
            "org = membersolutionsinc\n"
            "project = DevOps\n"
            "work_item_type = Issue\n",
            encoding="utf-8",
        )
        print(f"Created config: {conf_path}")
        print("  Edit this file to add your PAT and configure defaults.\n")

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


def _get_config(args) -> dict:
    """Build merged config from all sources."""
    cli_overrides = {
        "pat": getattr(args, "pat", None),
        "org": getattr(args, "org", None),
        "project": getattr(args, "project", None),
        "work_item_type": getattr(args, "type", None),
    }
    return load_config(cli_overrides)


# ── CLI Setup ────────────────────────────────────────────────────────────────


def main():
    # Parent parser with shared global flags (inherited by all subcommands)
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--org", "-o", help="Azure DevOps organization")
    parent.add_argument("--project", "-p", help="ADO project name")
    parent.add_argument("--type", "-t", help="Default work item type (Issue, Task, Bug, etc.)")
    parent.add_argument("--pat", help="Personal access token (prefer config file or env var)")
    parent.add_argument("--config", "-c", help="Path to config file")
    parent.add_argument("--verbose", "-v", action="store_true", help="Print request details")

    parser = argparse.ArgumentParser(
        prog="ticky",
        description="CLI utility for injecting work items into Azure DevOps",
        parents=[parent],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser(
        "create", parents=[parent], help="Create work item(s) from a YAML/JSON file"
    )
    p_create.add_argument("file", help="Path to ticket YAML/JSON file")
    p_create.add_argument(
        "--dry-run", "-n", action="store_true", help="Show payload without creating"
    )
    p_create.set_defaults(func=cmd_create)

    # validate
    p_validate = subparsers.add_parser(
        "validate", parents=[parent], help="Validate a ticket file (no API call)"
    )
    p_validate.add_argument("file", help="Path to ticket YAML/JSON file")
    p_validate.set_defaults(func=cmd_validate)

    # init
    p_init = subparsers.add_parser(
        "init", parents=[parent], help="Generate template config and example ticket"
    )
    p_init.set_defaults(func=cmd_init)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
