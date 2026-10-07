# LeadZen logo assets — October 3, 2026

The current app uses the complete logo artwork, including “by Zyene” and TM.
`dashboard/public/brand/leadzen-by-zyene-approved-light.png` is the owner's latest
2170 × 725 attachment copied without modification. The complete existing
`leadzen-by-zyene-dark.png` is the matching dark variant. Both are wired into
the shared `Brand` component for login, setup, password, Workspace, and Chat.
The earlier compact logos and native-attribution implementation described below
are preserved as release history. The favicon continues to use the same mark.

Created with the **built-in image-generation tool**, from the logo screenshot
supplied by the user. No fallback API or external image service was used.
The reference's folded L and horizontal wordmark are preserved, using Zyene's
ink/paper palette in place of its blue/purple gradient.

## Deliverables

- `leadzen-user-reference.png`: preserved copy of the supplied logo screenshot.
- `leadzen-logo-light-master.png`: original high-resolution light artwork,
  2168 × 725, transparent.
- `leadzen-logo-dark-master.png`: original high-resolution reversed artwork,
  2168 × 725, ink backdrop.
- `leadzen-mark-master.png`: original icon artwork, 1254 × 1254, transparent.
- `leadzen-by-zyene-light-master.png` and `leadzen-by-zyene-dark-master.png`:
  complete logo artwork including “by Zyene” and superscript TM, 2170 × 725.
- `../../dashboard/public/brand/leadzen-by-zyene-light.png` and
  `../../dashboard/public/brand/leadzen-by-zyene-dark.png`: complete logo exports
  at 1200 × 401 for reuse outside the app.
- `../../dashboard/public/brand/`: cropped 768 × 188 horizontal logos, PNG
  icons at 16, 32, 48, 180, 192 and 512 pixels, and a multi-resolution ICO
  containing 16/32/48-pixel PNG frames.

Sharp was used only for production cropping, resizing and PNG export. Generated
artwork was not redrawn. The generated originals remain in Codex's image directory.
The dark artwork uses CSS contrast and lighten blending so its backdrop merges
with both the dark canvas and raised cards. Transparent light/icon alpha is
preserved. Native Space Grotesk Bold type renders “by Zyene” at 14px with a small
superscript TM below the wordmark in the app. The original wordmark images omit
attribution to avoid duplicating that native text. The complete logo exports
include attribution in the artwork, following the user's additional request.

The shared `Brand` component installs these assets across login, setup, password,
Workspace and Chat. Root metadata declares the matching browser/home-screen
icons. The public `/brand/` directory is accessible before authentication;
application records and API routes remain protected.
Validation and browser checks are recorded in
[../logo-validation-2026-10-03.md](../logo-validation-2026-10-03.md).

## Accepted prompts

### Light logo

> Use case: precise-object-edit / logo-brand. Edit the attached Leadzen logo reference into a polished horizontal product logo for LeadZen by Zyene. Preserve the recognizable rounded-square badge and white folded L formed by the two smooth geometric pieces, and preserve the horizontal icon-left, wordmark-right layout. Replace ALL blue/purple/gradient styling with the established Zyene monochrome palette: badge and every letter solid ink #0A1015, negative-space L solid white #FFFFFF. Exact wordmark text: "LeadZen", uppercase L and Z, all other letters lowercase. Use a crisp contemporary geometric sans matching Geist, balanced bold weight, precise letter spacing; no extra tagline or TM in this image (the app will render the Zyene attribution separately). Keep original symbol identity, refine alignment and optical spacing; clean flat vector-like edges. Transparent background, no white rectangle, no shadows, no glow, no gradients, no mockup, no scene, no extra marks. Produce ONE finished high-resolution horizontal logo, comfortably contained with even small clear space.

Input: user screenshot. `transparent_background: true`.
Original: `exec-242a9be2-13e8-439d-99a0-3d20eba77119.png`.

### Dark logo

> Create a pristine professional monochrome DARK-MODE horizontal product logo, guided by this approved reference. Exact text "LeadZen" in solid paper #FBFBFA, bold contemporary geometric sans, icon left of text. Same rounded-square badge with the same folded L made from two smooth geometric pieces: badge paper #FBFBFA and folded L ink #0A1015. Background MUST be uniform solid ink #0A1015, an opaque flat rectangle. This is a finished flat logo asset on a dark background, no transparency. Preserve the reference proportions and recognizable geometry. Clean continuous smooth letter strokes and crisp edges; no texture, no speckles, no noise, no shading, no distressed outline, no gradient, no shadows or glow. One logo only, horizontal aspect ratio, small consistent empty margins. Do not cut out or remove any background.

Input: accepted light logo. `transparent_background: false`.
Original: `exec-abdf59c7-29be-4628-910d-23f0f9739dcd.png`.
Transparent dark experiments had edge artifacts and were not installed.

### Favicon / standalone mark

> Use case: logo-brand / precise-object-edit. Extract the recognizable ICON ONLY from the attached LeadZen logo for a professional favicon. ONE centered square mark, no words or letters outside the symbol. Solid ink #0A1015 rounded-square badge with the same white #FFFFFF folded geometric L formed by two smooth leaf-like pieces separated by a diagonal gap. Preserve the icon identity, improve optical centering and crispness at tiny 16px and 32px sizes. Flat vector-like continuous opaque surfaces, no gradients, no texture, no noise, no shadow, no glow, no outlines, no extra shapes. Badge occupies approximately 90 percent of the square canvas, with equal narrow transparent outer margins and transparent rounded corners. High-resolution square PNG, transparent background.

Input: accepted light logo. `transparent_background: true`.
Original: `exec-753d8099-81b1-4522-a3ba-98d22752321b.png`.

### Complete light logo with attribution

> Use case: precise-object-edit / logo-brand. Edit target: attached finished LeadZen light logo. Add the exact attribution text "by Zyene" beneath the LeadZen wordmark, aligned with the left edge of the wordmark rather than the badge. Add a tiny superscript TM immediately after Zyene. Use Space Grotesk Bold style for this attribution, approximately 26 percent of the LeadZen capital-letter height, with comfortable spacing so it remains legible at app-header sizes. Preserve the exact LeadZen text, capital L and Z, existing folded-L symbol, rounded-square badge, letter shapes and horizontal arrangement. Ink #0A1015 for all wordmark and attribution text and the badge; white #FFFFFF folded L. Extend transparent canvas downward only as needed, equal quiet clear space. One finished horizontal brand lockup, with "by Zyene" clearly readable. Flat crisp clean continuous shapes, transparent background, no added tagline, no gradient, no shadow, no noise, no texture, no scene.

Input: light wordmark export. Built-in tool, `transparent_background: true`.
Original: `exec-4b303d5f-21c5-49b4-80c9-2ad9a6b2bcae.png`.

### Complete dark logo with attribution

> Use case: precise-object-edit / logo-brand. Edit target: attached finished DARK-MODE LeadZen horizontal logo. Add ONLY the exact attribution text "by Zyene" with a clearly visible space between "by" and "Zyene", beneath the LeadZen wordmark, left-aligned with the LeadZen text. Add tiny superscript TM immediately after Zyene. Use Space Grotesk Bold style for attribution, approximately 26 percent of LeadZen capital-letter height, comfortably spaced and readable. All attribution text paper #FBFBFA. Preserve existing paper LeadZen letters, exact L/Z capitalization, paper rounded-square badge, ink folded L, icon geometry and horizontal composition. Background must remain uniform opaque solid ink #0A1015, no transparency. Extend canvas down only enough for the attribution and margins. One clean flat horizontal complete logo lockup, no other changes, no gradient, no glow, no shadow, no noise, no texture, no outlines, no extra tagline or scene.

Input: dark wordmark export. Built-in tool, `transparent_background: false`.
Original: `exec-6c0e14be-b7f4-4a21-a0f4-42969b3581c2.png`.
