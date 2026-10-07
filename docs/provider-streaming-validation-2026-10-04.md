# Provider streaming validation — October 4, 2026

Local implementation and validation only; no deployment, real mail or enrichment.
The existing Chat streaming implementation was inspected before changing code.

## Already implemented

- `leadzen/ai.py` constructs the installed Pydantic AI adapters and vendor SDKs for
  OpenAI, OpenAI-compatible, Groq, Anthropic, Google, Mistral and Cohere. Both modern
  and legacy HTTP clients use the same bounded, pinned HTTPS transport. Streaming
  reads use `read1`, close the connection, and recheck task/access guards.
- `leadzen/chat/engine.py` validates the model's `Decision`, saves received visible
  text under one assistant-message ID, and validates final output before dispatch.
  Domain tools, exact approvals, employee isolation and request budgets are shared
  with Workspace. Neither JSON text nor tool arguments grant authority to send.
- Authenticated backend SSE contains canonical conversation snapshots, not vendor
  wire events. The Next.js proxy forwards the response body without buffering.
  `dashboard/lib/chat-stream.ts` and the existing Chat components consume only
  that application format. Markdown, cursor, scrolling, Stop, reconnect and saved
  history were already present. No Chat UI or frontend stream parser was changed.

## Missing pieces and changes

1. The installed Cohere model adapter does not override `Model.request_stream`.
   Chat now checks that capability before I/O and uses the adapter's normal,
   validated `run_sync` path. It shows a completed answer without simulated tokens.
   A failed or partial stream is never replayed through this fallback.
2. Cohere's underlying SDK defaults to implicit retries and does not expose the
   same public retry property as the other clients. Its constructor now explicitly
   receives `max_retries=0`, preserving the existing request budgets.
3. Some OpenAI-compatible gateways stream content but buffer structured tool-call
   arguments. Chat has a server-only opt-in for Pydantic AI `PromptedOutput(Decision)`:

   ```sh
   LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS=api.akashml.com
   ```

   This is an example for a validated gateway, not a deployment instruction. The
   setting matches exact, comma-separated hostnames and applies only to the saved
   `openai_compatible` provider. Defaults retain existing tool output. It changes
   only Chat output encoding; shared draft/qualification model factories are
   unaffected. The same strict final schema, typed tool validation and approval
   checks still run. It neither approves a new endpoint nor enables network access:
   custom hosts still require the existing `LEADZEN_LLM_HOSTS` approval.

   Validate each chosen model before enabling this setting for a host, since it
   applies to every Chat model on that host. Prompted JSON is not constrained tool
   output and can be malformed; existing bounded validation handles that failure.
4. Added real vendor-SDK wire fixtures and an answer-only disposable live harness.
   The fixtures mock HTTPS response bytes rather than Pydantic's normalized model
   output. The live harness blocks every domain action, uses 512 output tokens and
   one provider request per run, disables validation retries, and reserves a
   cumulative request budget before I/O. Default lifetime budget is three, with an
   explicit maximum of five. Restarting cannot reset its ledger.
5. Added `dashboard/.gitignore` coverage for `.env*.local`; the user-supplied local
   credential file was previously unignored. Its contents were not changed or
   recorded in source, logs, screenshots or test evidence.

## Protocol verification

Installed Pydantic AI 2.52.0 and the repository's installed SDKs were exercised.
Dependency versions and constraints were not changed in this work.

| Connection | Actual adapter format tested | Result / limitation |
| --- | --- | --- |
| OpenAI / OpenAI-compatible | Chat Completions `data:` SSE, split tool arguments | Progressive validated Decision; same application SSE |
| Compatible host opt-in | Chat Completions `delta.content` containing JSON | Progressive validated Decision; same application SSE |
| Groq | Native SDK, Chat Completions SSE | Progressive split tool arguments |
| Anthropic | Named SSE events, `input_json_delta`, lifecycle/error events | Progressive split tool arguments |
| Google | `streamGenerateContent?alt=sse`, native complete `functionCall.args` | Valid normalized Decision; complete tool args may appear together |
| Mistral | Native SDK chat-completion SSE, complete tool arguments | Valid normalized Decision; complete tool args may appear together |
| Cohere | Native SDK `/v2/chat`, non-streaming structured tool result | Buffered validated answer; 429/500 do not trigger implicit retries |
| Unsupported compatible response | Buffered JSON / NDJSON returned to a streaming request | Safe failed task; no raw response exposed, no fallback replay |

Fixtures include fragmented CRLF frames and UTF-8, output before network EOF,
truncation, invalid tool names, provider errors, socket closure, task cancellation,
exact-host opt-in restrictions, canonical authenticated SSE, final persistence and
duplicate-dispatch prevention. Cohere tests include late cancellation, inert replay
of a failed request ID, and a new explicit retry succeeding with one new request.

## Real browser test

The user explicitly supplied the existing server-side configuration file for this
test. It selected AkashML at `https://api.akashml.com/v1`, initially
`moonshotai/Kimi-K3`. Only synthetic writing prompts and disposable fixture records
were used. The original file was retained unchanged.

Five total provider requests were reserved:

- Requests 1–3: Kimi's default structured tool output rendered and persisted valid
  complete Markdown answers. Observations did not show progressive visible text.
- Request 4: Kimi with prompted JSON received HTTP 200 `text/event-stream` and
  491 nonempty transport chunks from 986 ms through 7,001 ms. It did not produce
  a valid visible Decision within the 512-token test budget, and the task failed
  safely. The exact reason was not established from content-free metadata. Kimi
  documents always-on reasoning, which may consume the bounded output budget;
  this is a possible explanation, not proven gateway diagnosis. No private
  reasoning was displayed or logged, and no automatic retry occurred.
- Request 5: `meta-llama/Llama-3.3-70B-Instruct`, on the same approved AkashML
  connection with prompted JSON, produced HTTP 200 `text/event-stream`. There
  were 142 nonempty transport reads, from 656 ms through 3,262 ms. The canonical
  assistant record grew **17 → 48 → 79 → … → 552 characters** under the same ID
  while the run was still `running`. Browser DOM samples showed growing visible
  text and the existing cursor. The existing **Stop task** button was clicked
  during generation: the run became `cancelled`, cursor disappeared and received
  text remained. Reload preserved the partial answer and prior completed replies.

The browser view was a narrow responsive viewport. Screenshots demonstrate real
retained Markdown and cancellation; timing evidence demonstrates progression:

- [Retained partial answer](ui-progress-assets/provider-stream-live-retained-2026-10-04.png)
- [Stopped run](ui-progress-assets/provider-stream-live-stopped-2026-10-04.png)
- [Browser DOM samples](ui-progress-assets/provider-stream-live-browser-2026-10-04.json)
- [Canonical persistence samples](ui-progress-assets/provider-stream-live-canonical-2026-10-04.json)
- [Transport timing/byte counts](ui-progress-assets/provider-stream-live-wire-2026-10-04.jsonl)
- [Reload/persistence proof](ui-progress-assets/provider-stream-live-reload-2026-10-04.json)

The live key was removed from disposable Settings afterward. The identified live
harness was stopped and the standard synthetic preview restored on ports 8000/3001.
Provider billing totals were not independently verified. No real email was sent.

## Automated checks

- **554 backend tests passed** across Chat, Chat AI, Chat Workspace and native
  provider wire formats. This run preceded three final additional test cases.
- **62 final focused provider tests passed** after adding Cohere cancellation and
  unsupported JSON/NDJSON protocol cases; includes all 37 final wire-format cases.
  One existing Pydantic event-loop deprecation warning remains.
- **172 frontend tests passed** across Chat stream protocol, experience,
  presentation and agent behavior. Existing frontend source was unchanged.
- Dashboard TypeScript check and optimized build passed; `git diff --check` passed.
- Live harness `--check` passed without network/provider calls.

Counts describe their actual scopes, not a full-repository certification or the
sum of unique tests. Earlier temporary test failures were corrected fixture
assumptions; production code was not broadened to satisfy those test fixtures.

## Remaining limits

One real provider connection was tested. Other provider formats have actual SDK
fixture coverage, not live-account certification. Kimi progressive output remains
unverified. Google/Mistral's current structured-tool adapters may expose completed
arguments together. The installed Cohere adapter remains buffered. Custom endpoints
must implement the supported OpenAI Chat Completions contract; arbitrary NDJSON,
Responses-only APIs, custom WebSockets and local HTTP endpoints are not supported.
An endpoint that ignores streaming is surfaced safely; it is not silently replayed
as another paid request. Stop cannot retract a request the provider already accepted.

Primary references: [Pydantic AI output modes](https://pydantic.dev/docs/ai/core-concepts/output/),
[AkashML model catalog](https://akashml.com/docs/platform/models),
[Kimi model behavior](https://www.kimi.ai/help/kimi-api/api-model-selection).
