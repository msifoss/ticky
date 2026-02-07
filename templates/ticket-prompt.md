# ADO Ticket Generator Template

Use this prompt with Claude to generate a ticky-compatible YAML ticket file. Copy everything below the line, fill in the bracketed placeholders with your request details, and paste it into a Claude session.

---

## Prompt to give Claude:

```
I need you to generate an Azure DevOps work item in YAML format. Follow this schema and formatting exactly.

**My request:**
[Describe what you need the ticket for. Be as detailed or brief as you want — Claude will flesh it out.]

**Work item type:** [Issue | Task | Bug | Epic | Feature — default: Issue]
**Priority:** [1 (Critical) | 2 (High) | 3 (Medium) | 4 (Low) — default: 2]
**Tags:** [semicolon-separated tags, e.g. "SharePoint; CXSM; Permissions"]
**Requestor:** [Your name]
**Email:** [Your email]

---

Generate the output as a YAML file using this exact structure:

title: "Short, specific title — under 100 characters"
type: Issue
priority: 2
tags: "Tag1; Tag2; Tag3"
description: |
  <h2>Description</h2>
  <p>Clear summary of what is being requested and why.</p>

  <h2>Background / Business Justification</h2>
  <p>Context on why this matters. What problem does it solve? What initiative does it support?</p>

  <h2>Scope & Details</h2>
  <ul>
  <li><strong>Key point:</strong> Detail</li>
  <li><strong>Key point:</strong> Detail</li>
  </ul>

  <h2>Steps to Complete</h2>
  <table border="1" cellpadding="6" cellspacing="0">
  <tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>Step</th><th>Action</th></tr>
  <tr><td>1</td><td>First action</td></tr>
  <tr style="background-color:#F2F6FA;"><td>2</td><td>Second action</td></tr>
  </table>

  <h2>Acceptance Criteria</h2>
  <table border="1" cellpadding="6" cellspacing="0">
  <tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>#</th><th>Criteria</th></tr>
  <tr><td>1</td><td>First criterion</td></tr>
  <tr style="background-color:#F2F6FA;"><td>2</td><td>Second criterion</td></tr>
  </table>

  <h2>Timeline</h2>
  <p>Requested completion: <strong>[timeframe]</strong></p>

  <h2>Contact</h2>
  <p><strong>Requestor:</strong> [Name]<br/>
  <strong>Email:</strong> [email]<br/>
  Available for questions or a quick call if needed.</p>

Rules:
- Output ONLY the YAML. No markdown fences, no explanation before or after.
- The description must be valid HTML inside a YAML literal block (the | character).
- Use the styled table format shown above for Steps and Acceptance Criteria.
- Alternate row backgrounds using style="background-color:#F2F6FA;" on even rows.
- Table headers use style="background-color:#1B3A5C;color:#FFFFFF;".
- Use <strong> for emphasis, not bold markdown.
- Use &amp; for ampersands in HTML.
- Keep the title concise but specific.
- Include all sections shown above. Omit a section only if it truly doesn't apply.
- If I didn't provide enough detail for a section, make a reasonable inference and flag it with [VERIFY] so I can review.
```
