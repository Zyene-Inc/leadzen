# Employee message bubbles — October 4, 2026

Local CSS refinement following the owner's ChatGPT screenshot reference.

**Before:** Employee messages already had right alignment, content-sized width and
20px corners, but their background was `--surface-soft`, which equals the canvas.
Their bubble shape was hard to distinguish from the surrounding conversation.

**After:** Only the employee-message rule now uses existing `--line` as its fill
and `--ink` for text: light `#E6E8EA` / `#0A1015`, dark `#2C3742` / `#FBFBFA`.
Existing radii, responsive widths, padding, 16px text and line-break handling are
retained. Immediately submitted messages inherit the same rule. Assistant output,
streaming, Markdown, task controls and persistence were not changed by this styling.

**Why:** A visible neutral bubble makes the employee's message easy to scan while
matching LeadZen's ink-and-paper colors. No decorative blue, border or shadow was
added. A two-character message remains a compact pill instead of a full-width box.

Checked in the actual synthetic local preview:

- Short **Hi** message: content-sized, right aligned, approximately 43 × 46px at
  the normal narrow viewport; 20px corners, correct theme fill and text colors.
- Both light/dark variants: text contrast approximately **15.57:1 / 11.71:1**.
- Multiline message with an unbroken long reference at 390px: bubble stayed inside
  the viewport, preserved line breaks and wrapped without horizontal overflow
  (`clientWidth=scrollWidth=333px`). At 1280px it retained the 85% width cap,
  `clientWidth=scrollWidth=653px`, and the same 20px corners.
- Immediate submitting state and stored state both use the bubble style. Saved
  messages survive reload. Temporary viewport and theme changes were restored.
- **172 existing Chat frontend tests passed**. Dashboard TypeScript and optimized
  build checks passed; whitespace validation passed. No new cosmetic test or
  React component/state changes were necessary.

Screenshots: [Light](ui-progress-assets/employee-chat-bubble-light-2026-10-04.png),
[Dark](ui-progress-assets/employee-chat-bubble-dark-2026-10-04.png),
[Mobile](ui-progress-assets/employee-chat-bubble-mobile-2026-10-04.png).
[Layout measurements](ui-progress-assets/employee-chat-bubble-layout-2026-10-04.json).
These are disposable synthetic records. The earlier authorized live-provider
validation is documented [separately](provider-streaming-validation-2026-10-04.md).
The standard synthetic preview remains available at `http://localhost:3001`;
this styling has not been deployed.
