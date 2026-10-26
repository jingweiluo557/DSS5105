# Conversation streaming API

`POST /api/v1/workflow/chat/stream` (also `/chat/stream`) accepts the same JSON body as `/api/v1/workflow/chat`. Send `Content-Type: application/json`; include `X-ThreadPilot-Token` when application access control is enabled.

```json
{"message":"Which orders are most at risk?","session_id":null}
```

Optional fields: `session_id` from the previous response, `selected_order_id` for initial order context, `review_draft_id` for review-reason editing, and `confirmation_id` for a reviewed action. Messages are limited to 1,500 characters. A model-generated confirmation is never sufficient to execute an action.

## Events

The response uses `text/event-stream` with UTF-8 JSON data:

```text
event: start
data: {"request_id":"..."}

event: delta
data: {"text":"The highest-priority orders "}

event: delta
data: {"text":"are listed below."}

event: done
data: {"answer":"...","state":{},"tool_calls":[],"evidence":[]}
```

The `done` example is abbreviated: its actual payload is the complete `ChatResponse`, including the persisted session ID in `state`. `delta.text` chunks concatenate to the visible answer. Planning and tool execution precede narration; model narration then emits actual upstream text chunks. Exact confirmation, draft or deterministic fallback messages may arrive in one chunk. There is no artificial typing simulation.

A `: keep-alive` comment is sent after 15 seconds without an event. `start` is immediate, not evidence that generation has completed. Read until `done` or `error`; HTTP 200 alone is not success.

```text
event: error
data: {"message":"Generation interrupted. Please retry.","request_id":"..."}
```

Request-schema/authentication failures can be ordinary HTTP errors before the stream starts. Errors during processing are stream events. If a provider fails before narration, eligible workflows return a clearly identified basic answer. A failure after partial text produces an error instead of silently appending a template.

## Client and deployment behavior

Use streaming `fetch` with a reader (POST is not supported by the native EventSource interface). Decode UTF-8 incrementally and buffer incomplete SSE frames. Render text safely; use final metadata for evidence/action cards. The frontend supports cancellation, retry, stable scroll position and a new-conversation guard against late events.

Disconnecting cancels the worker and upstream stream. It does not undo a write or saved draft that already completed. An interrupted partial answer is not a completed saved conversation turn. Retry confirmed actions with the same confirmation ID to preserve idempotency.

Disable reverse-proxy response buffering and compression modes that batch SSE. Preserve `Cache-Control: no-cache` and `X-Accel-Buffering: no`; configure gateway timeouts for the full request, including planning and tools. Some gateways ignore these headers: verify time to first text and multiple incremental chunks through the actual public HTTPS endpoint before release.
