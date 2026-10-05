# Security policy

## Report a vulnerability

Please report suspected vulnerabilities privately to [support@zyene.com](mailto:support@zyene.com) with the subject line `LeadZen security report`. Do not open a public GitHub issue for a suspected vulnerability.

Include enough information for us to reproduce and assess the issue:

- affected component, version, or commit
- a clear description of the potential impact
- safe reproduction steps or a proof of concept
- any relevant logs, with credentials, personal data, and customer information removed

We will acknowledge the report, assess the impact, and coordinate a fix or mitigation. Please give Zyene time to investigate before sharing technical details publicly.

## Security boundaries

LeadZen handles employee workspace data and connections to company mailboxes, AI providers, and lead-discovery services. Contributors must keep credentials server-side, validate canonical records on the server, preserve workspace isolation, and enforce approval at the actual external action.

See [CONTRIBUTING.md](CONTRIBUTING.md) for day-to-day contribution rules and the production documentation in [`docs/`](docs/) for operational controls.
