# LeadZen by Zyene privacy information

This internal company build stores campaign descriptions, lead records, mailbox
settings, and outreach history in the company's database. Mailbox passwords and AI
keys entered through the dashboard are encrypted on the API server and are never
returned by settings reads.

The configured AI provider receives the prompt information needed to qualify
leads and compose messages. BetterContact or another configured address provider
processes discovery and enrichment requests under its own terms. Zoho or the
configured mail provider handles SMTP sending and IMAP reading.

The installed finder also supports a third-party shared contacts service. Its
configured endpoint and token determine that integration; it is not a contacts
service owned by Zyene. The original provider's data practices and any applicable
consent or objection requirements continue to apply. Renaming the application
does not transfer ownership of third-party services.

The operator remains responsible for the data they process, applicable retention
and deletion requirements, and handling access or objection requests. The sender
maintains a suppression list to honor opt-outs in the outreach workflow.

Zyene owns LeadZen. Zyene Reviews is a separate Zyene product employees may
promote through this tool. Account emails, hashed passwords, hashed revocable
sessions, setup purpose and administrator audit events are stored in the control
database. Each employee's leads, mailbox configuration and campaigns are kept
in a separate private workspace database. Deleting an account immediately revokes
access but retains its history for company retention review; it is not a
data-erasure request. Old CLI data is retained separately and is not automatically
exposed to new employee accounts.

Contact [support@zyene.com](mailto:support@zyene.com) for platform support or data
requests. An outreach sender's mailbox is not the platform support address.
See [LEGAL_NOTICE.md](LEGAL_NOTICE.md) for integration
and sender responsibilities and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for source provenance.
