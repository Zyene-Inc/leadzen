# Third-party source and licenses

LeadZen by Zyene is a modified company build derived from the GPL-licensed
[OpenOutreach project](https://github.com/eracle/OpenOutreach). Its original source
and author attribution are preserved here for provenance, separately from the
product interface. The original project's authors retain their rights in their
contributions. Zyene's modifications include the private dashboard, editable
connection settings, product branding, and suppression of tool attribution in emails.

The finder and sender dependencies remain their independently licensed packages:

- [OpenOutFind](https://github.com/eracle/OpenOutFind), package `openoutfind`.
- [OpenOutSend](https://github.com/eracle/OpenOutSend), package `openoutsend`.

See [LICENCE.md](LICENCE.md) for the GNU GPL terms. Bundled dependencies retain
their own license and copyright notices. This product rename does not rename or
transfer ownership of any third-party service, package, or source repository.

## Self-hosted fonts

Geist, Geist Mono and Archivo are bundled as WOFF2 files in
`dashboard/app/fonts`. Their source files come from the
[Google Fonts source repository](https://github.com/google/fonts), under the
SIL Open Font License 1.1. Each family's original copyright and license notice
is retained alongside the font as `<family>-OFL.txt`. WOFF2 compression changes
the delivery format; the typeface designs are unchanged.

The active LeadZen logo and browser icons were generated with the built-in image
tool from the logo reference supplied by the user, using Zyene's ink-and-paper
palette. Masters and prompts are recorded in `docs/brand-assets`. The older
website icon files are retained locally but are no longer referenced by the app.

## UI components and tooling

The dashboard uses [DaisyUI 5](https://github.com/saadeghi/daisyui) and
[Tailwind CSS 4](https://github.com/tailwindlabs/tailwindcss), both MIT licensed.
Their original license notices are retained in the installed packages.
The official DaisyUI Codex skill is installed in `.agents/skills/daisyui`.
[UI Skills](https://www.ui-skills.com) baseline guidance was read through its
CLI to support the existing product's visual and accessibility conventions.

## Warmbly (Apache License 2.0)

Parts of LeadZen's deliverability features are ported from
[Warmbly](https://github.com/warmbly/warmbly), Copyright 2026 Mindroot Ltd,
licensed under the Apache License, Version 2.0. The full license text is in
[licenses/warmbly-APACHE-2.0.txt](licenses/warmbly-APACHE-2.0.txt). Warmbly
publishes no NOTICE file. Apache-2.0 code may be combined into this
GPL-3.0-or-later project; the combined work is distributed under the GPL, and
the ported files keep Warmbly's copyright and Apache-2.0 notice.

The source is Warmbly commit `0df02b570cdca6ea567bd70887a4da6f5cc170a1`. Warmbly
is written in Go; Zyene translated the logic, rules and data to Python and
modified them for LeadZen. Each derived file names its sources in its header.

| LeadZen file | Warmbly source | What was taken |
| --- | --- | --- |
| `leadzen/dsn.py` | `internal/pkg/dsn/dsn.go`, `internal/pkg/dsn/cause.go` | Bounce (DSN) detection and parsing, permanent-versus-transient rules, failure-cause markers and status-code rules |
| `leadzen/arf.py` | `internal/pkg/arf/arf.go`, `internal/pkg/arf/mime.go` | Spam-complaint (ARF feedback-loop) detection and parsing |
| `leadzen/mail_signals.py` | `internal/app/worker/wmail/bounce.go`, `internal/app/advanced/inbound_bounce.go`, `internal/app/advanced/service.go` | Which reports block an address, resolving a report to the original send, never guessing a recipient |
| `leadzen/domain_health.py` | `internal/pkg/dnsauth/dnsauth.go`, `internal/app/advisor/detect_deliverability.go` | SPF/DKIM/DMARC record rules, DKIM selector lists, DMARC inheritance, special-use domains, fix steps and record values |
| `tests/test_mail_signals.py` | `internal/pkg/dsn/*_test.go`, `internal/pkg/arf/arf_test.go`, `internal/pkg/dnsauth/dnsauth_test.go` | Test cases adapted to the Python port |
| `leadzen/reply_classify.py` | `internal/app/replyclassify/classifier.go`, `headers.go`, `lexicon.go`, `optout_command.go`, `optout_languages.go`, `returndate.go`, `languages.go` (base and German rules) | Rule-based reply classes, automated-message headers, out-of-office subjects, quote stripping, opt-out and sentiment phrases, return-date parsing |
| `leadzen/reply_phrases.py` | `internal/app/replyclassify/lexicon.go`, `internal/app/replyclassify/optout_languages.go` | Opt-out phrase lists in English, German and 42 other languages, extracted unchanged |
| `leadzen/reply_sorting.py` | `internal/app/advanced/reply_optout_recheck.go`, `internal/app/inboxtag/followup.go`, `replyclassify.IsAutomated` | Unsubscribe replies go on Do not contact; out-of-office replies hold follow-ups until the next business day after the return date; away messages are not human replies |
| `tests/test_reply_sorting.py` | `internal/app/replyclassify/*_test.go` | Return-date, opt-out and header test cases adapted to the Python port |
