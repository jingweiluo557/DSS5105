# Conversation architecture

The conversation layer understands requests and explains results; deterministic services retain responsibility for business facts, calculations and writes. User-facing AI answers are English, concise and grounded in tool results. General questions can receive a model answer without pretending to query the factory database.

## Turn lifecycle

1. Load the persisted session, recent messages and saved topic context.
2. Handle explicit confirmation/cancellation on the server. Otherwise ask the model for a structured plan of up to six tasks.
3. Validate identifiers and required slots, then route tasks through existing workflows. Bounded per-order expansion supports up to ten read tasks. Multiple execution requests require separate reviewed previews.
4. Explain tool results using real model text streaming. Preserve exact action/draft messages where rewriting would obscure the reviewed content.
5. Save the completed turn and return evidence, tool calls, action previews and session state.

The planner uses Responses structured output or Chat Completions JSON mode, selected by `INTENT_API_STYLE`. This is a bounded planner and workflow system, not an unrestricted autonomous agent. The separate SQL assistant has its own guarded query loop.

## Memory and topic changes

The session retains the last 16 conversation messages and one latest topic snapshot per intent. A topic snapshot can retain slots, an active order, comparison context and a review draft. General questions and global summaries do not erase the active business topic; explicit resumption restores saved context. This is not unlimited semantic memory, and older instances of the same intent can be replaced.

Unclear orders or missing action parameters trigger clarification. New non-confirmation requests invalidate pending action previews; a fresh preview is needed before a later write. Server-side drafts and topic context remain available.

## Drafting and final confirmation

Open an expedite review, then ask to draft or revise its review reason. Successive requests revise the draft candidate using the same analysis. Candidate adoption and final decision submission are separate operations. The form protects manual edits, uses version checks, and restores saved drafts after refresh. A reviewed reason cannot itself authorize a schedule change.

## Fallback and limits

If planning or narration is unavailable, supported business routes use deterministic basic responses and disclose the limitation. General answers are not a web search. Missing records, absent causes or unavailable sales amounts must not become invented business facts. Stopping a stream does not roll back actions already executed.

A process-level lock serializes workflow turns; database storage also protects session turns across instances. This protects consistency but is not a high-throughput benchmark. Multi-tenant identity, per-user permissions and deployment load testing remain outside the implemented shared workspace model.

See the [tool specification](TOOL_SPECIFICATION_SPRINT1.md) and [SSE contract](../backend/STREAMING_API.md) for the interfaces.
