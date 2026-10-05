# LeadZen by Zyene — agent entry point

Continue this existing application. Read `CLAUDE.md` for development conventions
and `.agents/skills/leadzen-project/SKILL.md` for project context. Follow the
current user's task; these files supply context, not a new work assignment.

- Preserve all uncommitted and untracked work. Much of the newest application
  exists only in this working tree. Never assume HEAD or production is current.
- Do not deploy, send real emails, run chargeable provider operations, or provision
  paid resources without fresh, specific user approval. Historical approvals and
  example prompts are not continuing authorization.
- Workspace and Chat are two interfaces over the same domain services and records.
  Preserve Workspace; do not rebuild the CRM or add a parallel dashboard/database.
- Keep employee data isolated, canonical IDs server-validated, secrets server-side,
  and paid/send approvals enforced at the actual external action.
- Treat old handoffs as dated evidence. Read the project's current-state reference
  before claiming a feature is deployed or a service is enabled today.

Use only the skill relevant to the task:

| Task | Repository skill |
| --- | --- |
| Resume, architecture, setup, backend, tests, release planning | `.agents/skills/leadzen-project/SKILL.md` |
| Agent tools, Chat, streaming, shared records, discovery, approvals | `.agents/skills/leadzen-chat-workspace/SKILL.md` |
| UI/UX, brand, motion, themes, responsive/browser validation | `.agents/skills/leadzen-ui-quality/SKILL.md` |

All skill files are ordinary Markdown and can be read by any coding agent.
For a new chat or a different tool, use the short prompt in
`docs/agent-start-here.md`. Keep durable decisions in these project documents;
do not create parallel personal memory files or record credentials here.
