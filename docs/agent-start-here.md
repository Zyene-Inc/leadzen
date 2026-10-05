# Starting a new LeadZen coding chat

Open this repository as the coding workspace. Codex can discover the project
skills; Claude has repository skill links and `CLAUDE.md`; other agents can read
the same Markdown directly. Discovery depends on the host application, so paste
this when starting elsewhere:

> Continue the existing LeadZen by Zyene project in this repository. Read
> AGENTS.md and .agents/skills/leadzen-project/SKILL.md, then its current-state
> reference. Load the Chat/Workspace or UI quality skill only if relevant to my
> task. Preserve all uncommitted work. Do not deploy, send real email, spend
> provider credits, or change production without my fresh approval. Distinguish
> dated verification from current runtime state. My task is: [describe the task].

The skills contain durable architecture, product and safety rules, implementation
maps, UI conventions, and verification procedures. The current-state reference
records the latest known local changes, release boundary, and test evidence:

[Current project state](../.agents/skills/leadzen-project/references/current-state.md)

After meaningful work, update that reference with what changed, what was actually
tested, what remains uncertain, and whether anything was deployed. Update the
relevant skill only when a reusable rule or implementation boundary changed.
Do not turn a one-off test failure into a permanent policy, copy secrets, or keep
multiple competing status files. Existing dated reports remain evidence.

The skills are project files, not cloud memory. Moving to another machine requires
copying the working tree (including untracked files) or an explicitly authorized
source-control save. Local skills alone do not make this work available remotely.
