# Agentic Workflow Conventions

The KYC pipeline is the heart of this project. The report calls it a "LangGraph agentic workflow" — in the current code it's a **hand-rolled, LangGraph-style pipeline** of pure functions over a single dataclass. Same shape, none of the dependency weight. These rules govern how to extend it without breaking the audit trail.

## Mental model

Each KYC case flows through an ordered list of **nodes**. A node is a pure function:

```python
def node_xxx(state: KYCState) -> KYCState:
    ...
    return state
```

The pipeline runner (`run_kyc_workflow` in `services/workflow_service.py`) walks the list once per case. State is mutated in place but the function signature returns it so node ordering reads cleanly.

```text
classify_documents → check_completeness → cross_validate → evaluate_face → make_decision
```

The decision is one of: `approved`, `flagged`, `rejected`, `incomplete`.

## State

`KYCState` is a `@dataclass` defined in `services/workflow_service.py`. Its shape:

- **Inputs** — `documents: list[dict]`, `face_verified: bool`, `face_confidence: float`
- **Per-node outputs** — `aadhaar_data`, `pan_data`, `validation` (a `ValidationResult`)
- **Final** — `decision`, `decision_reason`, `flags: list[str]`, `recommendations: list[str]`

**Rules:**

- One state object per case. Never share state between concurrent cases.
- Never reach into a node from outside the pipeline — call `run_kyc_workflow(...)` only.
- Adding a field is free. Removing one is a breaking change because `kyc_state_to_dict` is the API contract.

## Adding a new node

1. Write a pure function `node_xxx(state) -> state`.
2. Decide where in `WORKFLOW_GRAPH` it sits — order matters because later nodes read what earlier ones wrote.
3. Append to `WORKFLOW_GRAPH`. Don't reorder existing nodes without a comment explaining why.
4. If the node can short-circuit the pipeline (e.g. completeness check), set `state.decision` to a terminal value early and have downstream nodes guard with `if state.decision == "incomplete": return state`.
5. Update `kyc_state_to_dict` if you added a field that should reach the frontend.
6. Add a test under `backend/tests/services/test_workflow.py` (when the test suite exists) — golden-string assertions on the decision + flags are the easiest regression net.

## Decision thresholds

The thresholds in `node_make_decision` are the project's risk policy. **Don't tweak them casually** — they were tuned against the validation scoring weights:

| Condition | Decision |
|---|---|
| Critical fail on Name **or** DOB | `rejected` |
| `overall_score ≥ 80` AND face OK | `approved` |
| `overall_score ≥ 60`, OR `≥ 40` with no critical fails | `flagged` (manual review) |
| Else | `rejected` |

`face_ok = state.face_verified or state.face_confidence >= 60`.

If you change a threshold:

- Update the comment block in `node_make_decision`.
- Re-justify against the validation weights (Name 0.5 / DOB 0.3 / DocType 0.1 / OCRConf 0.1).
- Add a test that pins the new boundary.

## Validation scoring

`validate_documents` in `services/validation_service.py` produces the score the workflow consumes. Each check is a `ValidationCheck` with `status` ∈ {`pass`, `fail`, `warn`, `skip`}.

- **Name** uses Jaccard token similarity after lowercasing and stripping Indian titles (`Mr.`, `Mrs.`, `Shri`, `Smt.`, `Km.`, `Kumari`, …). Add new titles to the list in `_normalize_name`, don't add a separate function.
- **DOB** is exact match after normalisation to `DD/MM/YYYY`.
- **`skip` status uses score 0.5** — neutral — so a missing field doesn't sink an otherwise-clean case. Keep this.
- **Add a new check** by appending a `ValidationCheck` to `checks` and a `(score, weight)` tuple to `weighted_scores`. Don't forget to keep the weights summing to 1.0 if you redistribute.

## Flags and recommendations

Two parallel lists in `KYCState`:

- **`flags`** — what *went wrong* or what's borderline. Shown to reviewers.
- **`recommendations`** — what the *user* should do next ("re-take the selfie in a well-lit environment"). Shown in the verdict UI.

Keep them short and actionable. Avoid mixing technical detail (`overall_score = 0.42`) into user-facing recommendations.

## Auditability

Because the pipeline is deterministic and ordered, you can replay any case by feeding the original `documents` list back into `run_kyc_workflow`. Two things that would break this:

- Pulling state from globals (don't do it).
- Calling external APIs from inside a node (cross_validate is local; if you add a node that hits a third-party service, log the request + response so the case can still be replayed).

## Roadmap items called out in the report (not yet implemented)

- **MediaPipe Face Mesh** liveness check — would slot in as a new node `node_check_liveness` between `node_evaluate_face` and `node_make_decision`. A failed liveness should force `rejected`, not `flagged`.
- **Gender / age estimation** — secondary cross-check; a mismatch would add a `warn`, not block a case on its own.
- **RAG over compliance documents** — currently the chat is plain Ollama. If RAG is added, keep retrieval inside `chat_service.py`; the workflow nodes should not depend on a vector store.
- **Admin module for case review** — a `flagged` decision should write a record somewhere reviewable. Today, no DB exists; this is the natural first persistence layer.

## Anti-patterns to avoid

- ❌ Adding a node that *also* mutates files on disk — keep IO outside the workflow nodes; call OCR / face verification first, pass results in.
- ❌ Skipping a node based on a feature flag — if a node shouldn't run, remove it from `WORKFLOW_GRAPH` for that build.
- ❌ Throwing exceptions inside a node — catch them and write a `ValidationCheck(status="fail", …)` so the case still produces a decision.
- ❌ Letting a node mutate inputs (`state.documents`) — copy if you need to transform.
- ❌ Returning early without setting `state.decision` — the runner doesn't enforce this; nodes must.
