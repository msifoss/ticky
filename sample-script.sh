#!/bin/bash
# ============================================================
# Create ADO Work Item: Graph Explorer Admin Consent Request
# Org: membersolutionsinc | Project: DevOps | Type: Issue
# ============================================================

echo ""
echo "=== ADO Work Item Creator ==="
echo "This will create an Issue in membersolutionsinc/DevOps"
echo ""

# Prompt for PAT securely (input hidden)
read -sp "Paste your ADO Personal Access Token: " PAT
echo ""
echo ""

if [ -z "$PAT" ]; then
  echo "❌ No PAT provided. Exiting."
  exit 1
fi

# Base64 encode for Basic auth
AUTH=$(echo -n ":${PAT}" | base64)

# HTML description with full ticket content
read -r -d '' DESCRIPTION << 'HTMLEOF'
<h2>Description</h2>
<p>Requesting admin consent for the <strong>Sites.Read.All</strong> delegated permission on Microsoft Graph Explorer for user <strong>cfossenier@membersolutions.com</strong>.</p>
<p>This permission enables read-only access to SharePoint site metadata (site names, document library structures, folder hierarchies, file names, and last-modified dates) through the Graph API. No write, delete, or modify capabilities are included.</p>

<h2>Business Justification</h2>
<p>The CXSM team is conducting a SharePoint structure audit to improve documentation organization, reduce content sprawl, and establish a scalable taxonomy for team playbooks, process docs, and operational content.</p>
<p>Current SharePoint organization has evolved organically without consistent structure or naming conventions, creating friction for the team and slowing down documentation workflows. This audit will produce a proposed reorganization plan that improves findability and reduces maintenance overhead.</p>
<p>The Graph API export will be used to map existing sites, libraries, and folder structures programmatically – significantly faster and more accurate than a manual audit.</p>

<h2>Scope &amp; Security Notes</h2>
<ul>
<li><strong>Permission type:</strong> Delegated (runs as the signed-in user, respects existing access boundaries)</li>
<li><strong>Permission level:</strong> Read-only (Sites.Read.All)</li>
<li><strong>Application:</strong> Microsoft Graph Explorer (Microsoft first-party application)</li>
<li><strong>No application-level permissions requested.</strong> No service principal or app registration required.</li>
<li>The user will only be able to read metadata for sites they already have access to. This does not expand their existing SharePoint access in any way.</li>
</ul>

<h2>Admin Steps to Complete</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>Step</th><th>Action</th></tr>
<tr><td>1</td><td>Navigate to Azure AD &gt; Enterprise Applications &gt; Microsoft Graph Explorer</td></tr>
<tr style="background-color:#F2F6FA;"><td>2</td><td>Go to Permissions tab</td></tr>
<tr><td>3</td><td>Grant admin consent for Sites.Read.All (delegated)</td></tr>
<tr style="background-color:#F2F6FA;"><td>4</td><td>Confirm consent is applied tenant-wide or scoped to requesting user</td></tr>
<tr><td>5</td><td>Notify requestor upon completion</td></tr>
</table>

<h2>Acceptance Criteria</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>#</th><th>Criteria</th></tr>
<tr><td>1</td><td>Sites.Read.All delegated permission consented for Graph Explorer in Azure AD</td></tr>
<tr style="background-color:#F2F6FA;"><td>2</td><td>cfossenier@membersolutions.com can run GET /v1.0/sites?search=* in Graph Explorer</td></tr>
<tr><td>3</td><td>Response returns SharePoint site metadata (site names, IDs, URLs)</td></tr>
<tr style="background-color:#F2F6FA;"><td>4</td><td>No write permissions granted – read-only access confirmed</td></tr>
</table>

<h2>Timeline</h2>
<p>Requested completion: <strong>Within 2 business days.</strong> The audit is part of an active CXSM initiative and is currently blocked pending this consent approval.</p>

<h2>Contact</h2>
<p><strong>Requestor:</strong> Chris Fossenier<br/>
<strong>Email:</strong> cfossenier@membersolutions.com<br/>
Available for questions or a quick call if needed.</p>
HTMLEOF

# Build the JSON payload
# Using jq-free approach for portability
PAYLOAD=$(cat << JSONEOF
[
  {
    "op": "add",
    "path": "/fields/System.Title",
    "value": "Admin Consent Required: Microsoft Graph Explorer – Sites.Read.All Delegated Permission"
  },
  {
    "op": "add",
    "path": "/fields/System.Description",
    "value": $(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$DESCRIPTION")
  },
  {
    "op": "add",
    "path": "/fields/Microsoft.VSTS.Common.Priority",
    "value": 2
  },
  {
    "op": "add",
    "path": "/fields/System.Tags",
    "value": "SharePoint; Graph API; Permissions; CXSM; Documentation Audit"
  }
]
JSONEOF
)

echo "📤 Creating work item in Azure DevOps..."
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "https://dev.azure.com/membersolutionsinc/DevOps/_apis/wit/workitems/\$Issue?api-version=7.0" \
  -H "Content-Type: application/json-patch+json" \
  -H "Authorization: Basic ${AUTH}" \
  -d "$PAYLOAD")

# Split response body and status code
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  # Extract work item ID and URL
  WI_ID=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','unknown'))" 2>/dev/null)
  WI_URL=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('_links',{}).get('html',{}).get('href',''))" 2>/dev/null)
  
  echo "✅ Work item created successfully!"
  echo "   ID:  ${WI_ID}"
  echo "   URL: ${WI_URL}"
  echo ""
  echo "🔗 Direct link: https://dev.azure.com/membersolutionsinc/DevOps/_workitems/edit/${WI_ID}"
else
  echo "❌ Failed to create work item (HTTP ${HTTP_CODE})"
  echo ""
  echo "Response:"
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  echo ""
  echo "Common fixes:"
  echo "  - Check your PAT has Work Items Read & Write scope"
  echo "  - Verify the PAT hasn't expired"
  echo "  - Confirm 'Issue' is a valid work item type in your project"
  echo "    (if not, let me know what types you use and I'll update the script)"
fi