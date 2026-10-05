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
