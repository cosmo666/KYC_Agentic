# Agentic Workflow Conventions

The KYC pipeline is now a **real LangGraph state machine** (not the hand-rolled list of pure functions the previous MVP used). Persistence is via `AsyncPostgresSaver`. Routing is conditional on `state.next_required`. These rules govern how to extend the graph without breaking the audit trail.

## Mental model

The graph has 8 nodes. Each node wraps an agent function and persists a slice of state. Wait states (`wait_for_*`, `done`) hand control back to the API caller — the graph halts and returns. The next inbound HTTP request resumes from the checkpointed state.

```text
greet → capture_name → intake_aadhaar → (wait_for_aadhaar_confirm)
                                       ↓ confirm
                                       intake_pan → (wait_for_pan_confirm)
                                                  ↓ confirm
                                                  validate → (wait_for_selfie)
                                                           ↓ capture
                                                           biometric → geolocation → decide → done
```

The `compliance` agent is **not part of this graph** — it's invoked side-channel from `routers/chat.py` when the orchestrator classifies the user message as `intent="faq"`. It writes its own table (`compliance_qna`) and records the Q+A back into the message thread.

## State (`apps/api/app/graph/state.py`)

`KYCState` is a `TypedDict, total=False`:

| Field | Type | Owner |
|---|---|---|
| `session_id` | `str` (UUID) | seeded by `chat.py`; required |
| `language` | `"en" | "hi" | "mixed"` | orchestrator |
| `user_name` | `str | None` | `n_capture_name` |
| `aadhaar` / `pan` | `dict` with `{file_path, extracted_json, confirmed_json, photo_path, ocr_confidence}` | upload/intake/confirm |
| `selfie` | `dict` with `{file_path, id}` | capture/biometric |
| `cross_validation` | `{overall_score, checks[]}` | validation |
| `face_check` | `{verified, confidence, faces_detected, predicted_gender, aadhaar_gender, gender_match}` | biometric |
| `ip_check` | `{country_ok, country_code, city_match, state_match, ip, city, region}` | geolocation |
| `messages` | `Annotated[list, add_messages]` | every router that talks to the user |
| `next_required` | `NextRequired` literal | every node that advances the flow |
| `decision`, `decision_reason`, `flags`, `recommendations` | terminal | decision (or geolocation on country gate) |

**Rules:**

- One state object per `thread_id` (`thread_id == session_id`). Never share state across sessions.
- Nodes return **delta dicts**, never the whole state. The `add_messages` reducer would otherwise double-count anything you didn't touch.
- The `messages` list is special — `add_messages` deduplicates by id and merges. Treat it as append-only from outside the graph.
- Adding a field is free. Removing one is a breaking change because the FE reads them via the `Widget` envelope.

## NextRequired literal

The whole flow is encoded as a `Literal` in `state.py`:

```python
NextRequired = Literal[
    "greet", "ask_name", "wait_for_name",
    "ask_aadhaar", "wait_for_aadhaar_image", "ocr_aadhaar",
    "confirm_aadhaar", "wait_for_aadhaar_confirm",
    "ask_pan", "wait_for_pan_image", "ocr_pan",
    "confirm_pan", "wait_for_pan_confirm",
    "cross_validate", "ask_selfie", "wait_for_selfie",
    "biometric", "geolocation", "decide", "done",
]
```

**`wait_for_*` and `done` are terminal for a single graph invocation** — `_route_from_current` returns `END` for them, so the graph halts and the API caller gets to respond. The next inbound HTTP request reads the checkpoint and resumes.

If you add a new step:

1. Add the literal to `NextRequired`.
2. Update `_route_from_current` in `builder.py` to map it to the right node (or to `END` if it's a wait state).
3. Add the node + its `add_conditional_edges` mapping (the same mapping appears on every node — keep them all in sync).
4. If it's a user-interactive step, add an entry to `STEP_WIDGETS` in `orchestrator.py` and (if a runtime widget) extend `widget_for(...)`.
5. Update the FE's `MessageList` widget switch and `WidgetHandlers` if a new widget type is involved.

## Adding a new agent

1. Create the agent file under `app/agents/`. Signature: `async def run_xxx(state: KYCState, db: AsyncSession, ...) -> dict` returning a delta.
2. Add a node wrapper `n_xxx` in `app/graph/builder.py`. It builds per-invocation clients (Ollama / DB / etc.) and forwards.
3. Register the node in `build_graph()` and in every `add_conditional_edges` map.
4. Update `_route_from_current` and the entry-point dict.
5. Add a write to a domain table if the agent's output should be queryable (use `pg_insert(...).on_conflict_do_update(...)` for idempotence).
6. Add tests under `apps/api/tests/agents/` — pure-logic tests (parsers, math, threshold boundaries) are the cheapest regression net.

## Decision thresholds

Encoded in `agents/decision.py:compute_decision`. The order of gates matters; **don't reorder casually**:

| Gate | Trigger | Decision |
|---|---|---|
| Country | `ip_check.country_ok == False` | `rejected` (also pre-set from `geolocation.py` before reaching `decide`) |
| Critical mismatch | `name_match_critical_fail` or `dob_match_critical_fail` in `flags` | `rejected` |
| No face | `face_check.faces_detected == False` | `rejected` (rare path; biometric usually loops back to `wait_for_selfie`) |
| Strong pass | `score ≥ 80` AND (`face_check.verified` OR `face_check.confidence ≥ 60`) | `approved` |
| Borderline | `score ≥ 60`, OR `score ≥ 40` with no critical fails | `flagged` |
| Else | — | `rejected` |

`face_ok = face_check.verified or face_check.confidence >= 60`. The `>= 60` band is generous on purpose — old PAN photos are blurry; the `flagged` lane catches what the strict-pass band misses.

If you change a threshold:

- Add a comment block in `compute_decision` explaining the new boundary.
- Re-justify against the validation weights (Name 0.5 / DOB 0.3 / DocType 0.1 / OCRConf 0.1).
- Add a test in `tests/agents/test_decision_thresholds.py` that pins the boundary.

## Validation scoring (`agents/validation.py`)

`cross_validate(aadhaar, pan, aadhaar_conf, pan_conf)` returns `{overall_score, checks}` where each check is `{name, status, score, detail}`.

| Check | Logic | Status thresholds | Weight |
|---|---|---|---|
| `name_match` | Jaccard token similarity after `normalize_name` | `pass ≥ 0.75`, `warn ≥ 0.5`, `fail < 0.5` | 0.5 |
| `dob_match` | Exact equality after `normalize_dob` (`DD/MM/YYYY`) | `pass` / `fail` only | 0.3 |
| `doc_type_sanity` | `aadhaar.doc_type == "aadhaar"` AND `pan.doc_type == "pan"` | `pass` / `fail` only | 0.1 |
| `ocr_confidence` | mean of `{high: 1.0, medium: 0.6, low: 0.2}[per-doc]` | `pass ≥ 0.7`, `warn ≥ 0.4`, `fail < 0.4` | 0.1 |

A `skip` status (a field is missing on one side) gets a neutral 0.5 score, so a missing field doesn't sink an otherwise-good case. Critical fails (`name_match` or `dob_match`) get appended as `{check}_critical_fail` in `state.flags` for the decision agent to consume.

To add a new check:

- Append a check function to `validation.py` and to the list inside `cross_validate`.
- Add a weight to `WEIGHTS`. Keep the weights summing to 1.0 if you redistribute.
- Add a test in `tests/agents/test_validation_math.py`.

## Flags and recommendations

Two parallel lists in `KYCState`:

- **`flags`** — what *went wrong* or what's borderline. Reviewer-facing, stored in `kyc_records.flags`.
- **`recommendations`** — what the *user* should do next ("re-take the selfie in better lighting"). Stored in `kyc_records.recommendations`, surfaced via the verdict widget.

Keep flags machine-readable (`face_verification_low_confidence`, `ip_city_mismatch`); keep recommendations human-readable. Don't mix `overall_score = 0.42` into a recommendation.

## Auditability

The graph is deterministic given the same inputs and same checkpoint. To replay a case:

- The full conversation lives in `messages` (one row per turn, ordered by `seq`).
- The full graph state at each step lives in the LangGraph checkpoint tables (created by `AsyncPostgresSaver.setup()` on first boot).
- Per-agent outputs live in their domain tables (`documents`, `validation_results`, `face_checks`, `ip_checks`, `kyc_records`, `compliance_qna`).
- File uploads live in `/data/uploads/<session_id>/`.

What would break replay:

- Pulling state from globals (don't do it).
- Calling third-party APIs from inside a node without logging the request + response. `geolocation.py` already logs the raw ipwho.is response into `ip_checks.raw` for this reason.
- Depending on wall-clock time inside an agent. Today no agent does; keep it that way.

## Stale-state recovery

If a deploy changes the `KYCState` shape, old checkpoints can fail to deserialise on resume. The recovery is documented in the plan's Appendix A: `docker compose exec postgres psql -c 'TRUNCATE checkpoints CASCADE;'`. Domain tables stay intact. **Don't drop the domain tables** — those are the audit trail.

## Roadmap items called out in the spec (not yet implemented)

- **Liveness check** (MediaPipe Face Mesh) — would slot in as a new node `n_liveness` between `biometric` and `geolocation`. A failed liveness should force `rejected`, not `flagged`.
- **Per-agent Langfuse `@observe()` decoration** — client is wired in `services/langfuse_client.py`; calls aren't yet decorated. One-line per function.
- **Aadhaar photo cropping** — biometric currently uses the full Aadhaar image as the reference; cropping the photo region would lift face-match accuracy. Would write `aadhaar.photo_path` from a new node or from `intake.py`.
- **Admin reviewer UI for `flagged` cases** — the data is there (`kyc_records.decision == "flagged"`); a reviewer SPA is the natural next product.

## Anti-patterns to avoid

- ❌ Adding a node that mutates files outside `/data/uploads/<session_id>/`.
- ❌ Skipping a node based on a feature flag — if a node shouldn't run, remove it from the graph for that build.
- ❌ Throwing exceptions inside a node — catch them and write a check / flag so the case still reaches a decision. The exception path silently corrupts the checkpoint.
- ❌ Letting a node mutate input lists (`state["flags"]`) directly — copy: `flags = list(state.get("flags") or [])`. Mutation in place plays badly with reducers.
- ❌ Returning early without setting `next_required` — the runner doesn't enforce this; nodes must.
- ❌ Calling a node directly from a router — routes always go through `graph.ainvoke(delta, config=thread)` so the checkpoint stays consistent.
- ❌ Calling Langfuse from inside the agent without `@observe()` — direct calls miss the trace context. (Once decoration is added.)
- ❌ Putting expensive imports at agent module top-level — DeepFace and TensorFlow are lazy-imported inside the function for a reason.
