# ADR 016: Tailored CVs as First-Class Artifacts (Dual Variants)

## Status

Accepted (2026-10-13)

Supersedes ADR 015 §5 ("Editing a tailored CV still happens on `/cv`") and
revisits the "Full CV rewrite by LLM" rejection in ADR 006.

## Context

ADR 006 chose a rule-based tailoring engine with an optional LLM *polish* layer,
and stored every result as a **new, non-current `master_cv` version** plus a
`generated_cvs` row that only held the PDF. That storage decision quietly made
tailored output a second-class citizen of the master document, and two problems
followed.

**1. Tailoring barely tailored.** `tailor_cv()` filtered and reordered
experience/project blocks and moved matched skills to the front — but the
summary, education, certifications and languages were copied **verbatim**, and
no prose was rewritten. `POST /api/jobs/{id}/tailor` therefore produced something
close to a reshuffled copy of the master CV. Worse, when a JD parsed no skills
(common for terse/short postings) the engine silently fell back to the top three
blocks and reported nothing, so the output looked tailored while being arbitrary.

**2. Tailored CVs leaked into the master CV history.** Because each run minted a
`master_cv` row, `GET /api/cv` — the *master CV* version list, shown on `/cv` in
the web client and on the Master CV screen on mobile — filled up with
`"Tailored for <job> at <company>"` entries. The master document's history was
no longer a history of the master document. `Application.cv_version` pointed at
those versions, so "which CV did I send?" was answerable, but only by joining
through rows that should never have existed.

Meanwhile the feature the users actually wanted was available: ADR 011 already
proved that an LLM can produce a whole `CVStructure` from raw text, validated by
Pydantic, with graceful degradation. Nothing prevented the same call from
*rewriting* an existing structure against a job description — except the ADR 006
rejection of "full CV rewrite", on the grounds of cost and hallucination risk.

## Decision

**1. A tailored CV is its own artifact.** `generated_cvs` gains
`structured_json` (the artifact's own content), `variant` (`rule` | `llm`) and
`updated_at`, and **drops** `master_cv_id`. `Application.cv_version` is replaced
by `applications.generated_cv_id` (FK → `generated_cvs.id`, `ON DELETE SET
NULL`). A tailor run no longer creates a `master_cv` row at all, so tailored
output cannot appear in `GET /api/cv` again.

**2. Two variants, always comparable.** `workers.tasks.tailor` produces:

- **`rule`** — always. The deterministic engine, strengthened: the summary now
  leads with the JD-matched strengths (`"… Core strengths: python, fastapi."`,
  naming only skills already present elsewhere in the CV, so nothing is
  invented), and a no-match fallback is reported explicitly as `used_fallback`
  instead of being silent. This variant stays fully deterministic — the legacy
  per-bullet `enhance_with_llm` rephrasing is no longer wired into the worker,
  precisely because it would break that property.
- **`llm`** — only when `TAILORING_LLM_VARIANT_ENABLED=true` *and* an enabled
  LLM config with an API key exists. A single completion rewrites the whole CV
  against the JD; the reply is parsed and **validated with
  `CVStructure.model_validate`** before it is trusted. Any failure (disabled,
  HTTP error, malformed JSON, schema violation) logs a warning and the run
  continues with the `rule` artifact only — the LLM can never fail a tailor run.

Idempotency is per `(user_id, job_id, source_master_cv_id, variant)`, enforced by
a unique index. Requesting "tailor again" therefore reuses artifacts rather than
accumulating them.

**3. Both variants are scored by the deterministic ATS scorer.** ADR 013's
scorer is run over each artifact in the worker, so the two scores are directly
comparable (and cached on the row, so the UI needs no recomputation). The
LLM-blended hybrid mode is deliberately *not* used here — a hybrid score would
not be comparable across variants. Instead the `llm` artifact's `ats_report` also
carries `llm_self_score`: the model's own 0–100 estimate of its rewrite, surfaced
in the UI as "The AI's own estimate", never mixed into the score.

**4. The user records what was sent.** The worker auto-links the application to
the **`rule`** variant only. The optional `llm` variant is linked when the user
explicitly picks it with *Use this one* (`PUT /api/applications/{id}` with
`generated_cv_id`) — there is no silent auto-link, because the system cannot know
which draft the user actually sent.

**5. Tailored CVs are edited where they live, not on `/cv`.** `PUT
/api/cv/generated/{id}` edits one artifact in place: it re-renders the stored PDF
and clears the now-stale ATS cache, and the master CV is untouched. The web CV
panel edits the tailoring-relevant fields inline (summary, skills, per-block
bullets); mobile gets a dedicated `TailoredCvEditor` screen inside the
Applications stack. The `/cv?generated=<id>` deep link is **removed** — that was
the last way tailored content could be written back into the master document.

**6. No fabrication is load-bearing, so it is enforced twice.** The rewrite
prompt states the constraint explicitly ("keep every fact — employers, titles,
dates, degrees, skills and languages — exactly as given: NEVER invent …"), and
the deterministic variant is always produced and always kept. A hallucinating
model can therefore produce a *bad second artifact*, never a missing one.

## Consequences

### Positive

- **The master CV is the master CV again.** `GET /api/cv` returns only versions
  of the master document; tailored output is invisible to it on both clients.
- **Tailoring actually tailors.** The summary is rewritten deterministically and
  an LLM rewrite is available for the prose the rule engine cannot produce.
- **Comparable choices.** Both variants are scored by the same engine, so "is the
  AI rewrite better for this job?" is an evidence-based question.
- **Edits are contained.** Changing a tailored CV can no longer accidentally
  create a master version (the failure mode that motivated ADR 015).
- **Idempotent and cheap by default.** With no LLM configured, behaviour and cost
  are exactly the deterministic engine's.

### Negative / Risks

- **ADR 006's "full CV rewrite" rejection is reversed.** Cost and hallucination
  risk are real; the mitigations are: opt-in flag, no-fabrication prompt, schema
  validation, the rule variant always kept, an ATS comparison, the artifact
  marked AI-generated in the UI, and no auto-link.
- **Two artifacts per job.** The panel has to explain a `rule`/`llm` choice and
  let the user change their mind. Accepted: it is one extra tap, and the
  alternative (pick for them) loses information.
- **`llm_self_score` is a model's self-report.** It is stored and shown as
  exactly that, never as a score — a sycophantic estimate is a real failure mode.
- **The migration is destructive in one direction.** `0019` deletes the orphaned
  tailored `master_cv` rows it prunes. `downgrade()` reconstructs equivalent
  versions from `structured_json`, but they get fresh ids and a generic
  "Tailored (restored)" label.
- **Two clients to keep aligned**, as with every UI decision since ADR 012.

## Alternatives Not Selected

| Option | Reason for Rejection |
| ------ | -------------------- |
| Keep tailored CVs as `master_cv` versions, filter them out of `GET /api/cv` | A tag column still means every tailored CV *is* a version of the master document — the mental model ADR 015 already tried and failed to fix |
| Store content only in `generated_cvs.structured_json` and never expose an editor | The artifact stays immutable, so tightening one bullet costs a whole re-tailor run and an LLM call |
| Replace the rule engine entirely with the LLM rewrite | Removes the deterministic, free, offline baseline ADR 006 exists to protect; tailoring would stop working without an API key |
| Score the LLM variant with the hybrid (LLM-blended) scorer | The two variants' scores would no longer be comparable, which is the point of running both |
| Auto-link the `llm` variant when it exists | The system cannot know which draft the user sent; silently claiming the AI rewrite was sent is a correctness bug in the tracker |
| Keep the `/cv?generated=<id>` deep link as a secondary editor | It re-opens the exact failure mode this ADR fixes: an edit becomes a new master version |

## References

- `app/models/generated_cv.py` (`structured_json`, `variant`),
  `app/models/application.py` (`generated_cv_id`),
  `app/models/enums.py` (`CVVariant`)
- `alembic/versions/0019_tailored_cv_artifacts.py` (upgrade + reversible
  downgrade that reconstructs tailored versions from `structured_json`)
- `app/services/cv_tailor.py` (`tailor_cv`, `_tailored_summary`,
  `generate_tailored_cv_with_llm`), `app/services/cv_schema.py`
  (`CV_JSON_SCHEMA`, shared with `cv_parser`),
  `workers/tasks/tailor.py` (dual-variant orchestration)
- `app/routers/cv.py` (`PUT /api/cv/generated/{id}`,
  `GET /api/cv/generated?job_id=`), `app/routers/applications.py`
  (ownership check on `generated_cv_id`), `app/services/ats_scorer.py`
- `frontend/src/app/shared/cv-panel/`, `frontend/src/app/components/cv-editor/`
  (deep link removed), `mobile/src/components/cv/CvPanel.tsx`,
  `mobile/src/screens/TailoredCvEditorScreen.tsx`
- ADR 002 (data model), ADR 006 (rule-based vs LLM tailoring), ADR 011 (CV
  import/parsing — the LLM structuring pattern reused here), ADR 013 (ATS
  scoring), ADR 015 (per-application workspace)
