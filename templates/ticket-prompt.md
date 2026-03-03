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
  <h2>TL;DR</h2>
  <p>Plain-language summary for non-technical readers. 2-3 sentences max explaining
  what is needed and why, as if explaining to someone unfamiliar with the system.</p>

  <h2>Description</h2>
  <p>Clear technical summary of what is being requested and why.</p>

  <h2>What's Needed</h2>
  <p><strong>One-sentence summary of the action required.</strong></p>

  <h2>Steps to Complete</h2>
  <table border="1" cellpadding="6" cellspacing="0">
  <tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>Step</th><th>Action</th></tr>
  <tr><td>1</td><td>First action with exact commands or console steps</td></tr>
  <tr style="background-color:#F2F6FA;"><td>2</td><td>Second action</td></tr>
  <tr><td>3</td><td><strong>Verify:</strong> How to confirm success<br/>
  <code>verification command here</code></td></tr>
  </table>

  <h2>Background</h2>
  <p>Context on why this matters. What problem does it solve? What initiative does it support?
  Include architecture context if relevant.</p>

  <h2>Reference</h2>
  <table border="1" cellpadding="6" cellspacing="0">
  <tr style="background-color:#1B3A5C;color:#FFFFFF;"><th>Item</th><th>Value</th></tr>
  <tr><td>Account</td><td>123456789012 (Account Name)</td></tr>
  <tr style="background-color:#F2F6FA;"><td>Region</td><td>us-east-1</td></tr>
  <tr><td>Key Resource</td><td><code>resource-name-or-arn</code></td></tr>
  <tr style="background-color:#F2F6FA;"><td>Repo</td><td><a href="https://link">repo-name</a></td></tr>
  </table>

  <h2>Impact if Not Resolved</h2>
  <p>What breaks or degrades if this isn't done? Be specific about user-facing or operational impact.
  Distinguish between hard blockers ("deployment cannot proceed") and soft degradation ("feature shows empty data").</p>

  <h2>Estimated Time</h2>
  <p><strong>N minutes</strong> (brief description of what the time covers)</p>

  <h2>Contact</h2>
  <p><strong>Requestor:</strong> [Name]<br/>
  <strong>Email:</strong> [email]<br/>
  Available for questions or a quick call if needed.</p>

Rules:
- Output ONLY the YAML. No markdown fences, no explanation before or after.
- The description must be valid HTML inside a YAML literal block (the | character).
- Use the styled table format shown above for Steps and Reference.
- Alternate row backgrounds using style="background-color:#F2F6FA;" on even rows.
- Table headers use style="background-color:#1B3A5C;color:#FFFFFF;".
- Use <strong> for emphasis, not bold markdown.
- Use &amp; for ampersands, &mdash; for em dashes, &rarr; for arrows in HTML.
- Keep the title concise but specific — under 100 characters.
- Always include: TL;DR, Description, What's Needed, Steps to Complete, Reference, Impact if Not Resolved, Estimated Time, Contact.
- Include Background section when context is needed (most tickets).
- Omit optional sections (Budget Estimate, Rollback, How to Verify) only if they truly don't apply.
- Steps should include exact CLI commands, console URLs, or click-by-click instructions where possible.
- The final step should always be a verification step.
- If you didn't get enough detail for a section, make a reasonable inference and flag it with [VERIFY] so I can review.
```
