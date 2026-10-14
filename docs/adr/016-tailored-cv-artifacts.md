# ADR 016: Tailored CVs as First-Class Artifacts (Dual Variants)

## Status

Accepted (2026-10-13)

Amended (2026-10-13): the env-only `TAILORING_LLM_VARIANT_ENABLED` switch was
removed. Enabling the LLM in Admin → LLM (with a stored API key) is now the
only opt-in for the `llm` variant — same guard, one place to configure it.

Amended (2026-10-13, again): two defects found in production are fixed.
**(a) A content-less artifact heals itself.** `generated_cvs.structured_json` is
nullable and rows written before this ADR exist with it NULL — an artifact with
nothing to preview. The tailor task used to treat such a row as "already
produced", so the empty card could never be regenerated. A row with no content
no longer satisfies the idempotency shortcut: the run rebuilds the artifact and
**repairs that same row in place** (same id, so `created_at`, the
`applications.generated_cv_id` link and the variant uniqueness all survive).
**(b) One transport for every LLM call.** `app/services/llm_client.py` is now
the only place a chat completion is issued (CV structuring, bullet rephrasing,
full-CV rewrite, ATS review). It disables the provider's chain-of-thought
(DeepSeek's `thinking: {"type": "disabled"}` — provider-specific, so it is never
sent to OpenAI), asks for a bare JSON object, and treats a `200 OK` with empty
`content` as a failure worth logging. Thinking-mode models otherwise spend
`max_tokens` on `reasoning_content` and answer with nothing, which silently
dropped every feature onto its rule-based fallback.

Amended (2026-10-13, third time): **the `llm` variant is now a *selection* with a
page budget**, and its page count is measured instead of assumed. The original
prompt asked the model to "rewrite the candidate's CV so it is maximally
relevant" *and* to "keep every fact … exactly as given" — an instruction set with
no way to shorten anything. Relevance could then only be demonstrated by adding
and splitting bullets, so the artifact came back several pages long and read like
a padded restatement rather than a tailored CV. The prompt now asks for a CV
produced **for the target job**, using the master CV as the *only source of
truth* / reference, `MAY omit` roles, projects and bullets that do not help this
application, and aims at `LLM_TARGET_PAGES` (2) pages — expressed as the levers
the model actually controls (how many roles and bullets to keep, how long the
summary is), because page length is decided by the template and the fonts, not by
the model. Truthfulness is unchanged and only re-scoped: every fact *included*
must be exactly as given, and roles may never be split or merged. No hard
numeric caps were added anywhere — the reply is still validated by
`CVStructure`, and a shorter structure is a valid answer. Two supporting fixes:
the master CV is trimmed into **valid JSON** for the prompt (`_fit_cv_for_prompt`
drops whole entries, least JD-relevant first, instead of byte-slicing the
serialised JSON, which handed the model a broken reference to fill from
imagination — logged as `llm_cv_input_truncated`); and the stored PDF's page count
is recorded as `cv_artifact_pages`, with `llm_rewrite_over_page_budget` warning
when the AI variant ignores the budget. Over budget is *reported, never
corrected*: nothing is trimmed afterwards, so an over-long artifact stays visible
and the rule variant stays available for comparison.

Amended (2026-10-14): **a content-less artifact is not listed as a CV.** Repair
in place only fires when a run happens, and until then the application CV panel
advertised the empty row as the job's CV: a lone `rule` variant with no body,
labelled *only the deterministic variant exists*, pointing at a missing LLM
rewrite that had nothing to do with it. The row has nothing to preview, edit or
score, so `GET /api/cv/generated` now withholds artifacts whose `structured_json`
is NULL (logged as `cv_artifact_without_content_hidden`; the web and mobile
panels filter again on their own side). The job reads as *No tailored CV yet* and
the *Tailor* button — the thing that performs the repair — becomes the way out.
The row itself is kept, and `GET /api/cv/generated/{id}` still serves it for a
direct fetch, so repairing in place keeps preserving `created_at` and the
`applications.generated_cv_id` link.

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
- **`llm`** — only when an enabled LLM config with an API key exists. A single
  completion rewrites the whole CV against the JD; the reply is parsed and
  **validated with `CVStructure.model_validate`** before it is trusted. Any
  failure (disabled, HTTP error, malformed JSON, schema violation) logs a
  warning and the run continues with the `rule` artifact only — the LLM can
  never fail a tailor run.

Both conditions gate `llm`, and *both* are silent when unmet (nothing fails, so
nothing warns). To make that debuggable, `_llm_variant_skip_reason()` names the
missing one and the worker logs `cv_tailored_llm_variant_skipped` whenever it
skips — `docker compose logs worker | grep llm_variant_skipped` answers "why do I
only see the deterministic CV?" directly. The CV panel shows the same
requirement next to a lone `rule` card, for the case where logs are out of
reach.

Idempotency is per `(user_id, job_id, source_master_cv_id, variant)`, enforced by
a unique index. Requesting "tailor again" therefore reuses artifacts rather than
accumulating them.

**3. Both variants are scored by the same deterministic ATS scorer, on demand.**
ADR 013's scorer is deliberately *not* run by the worker: each artifact is stored
with `ats_score`/`ats_report` NULL and is scored when the user asks
(`POST /api/cv/ats-score`), so the two numbers are directly comparable **and** a
tailor run never pays for a score nobody requested. The LLM-blended hybrid score
is not used: the report carries the deterministic score and the LLM's own
estimate as separate fields. The one value captured at generation time is the
`llm` artifact's `llm_self_score` — the model's own 0–100 estimate of its
rewrite, surfaced in the UI as "The AI's own estimate", never mixed into the
score.

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
prompt states the constraint explicitly ("Every fact you include — employers,
titles, dates, degrees, skills, numbers and languages — must be exactly as given
in the master CV: NEVER invent … and never split or merge roles"), scoped to the
facts that *are* included so that selecting is still possible, and the
deterministic variant is always produced and always kept. A hallucinating model
can therefore produce a *bad second artifact*, never a missing one.

## Consequences

### Positive

- **The master CV is the master CV again.** `GET /api/cv` returns only versions
  of the master document; tailored output is invisible to it on both clients.
- **Tailoring actually tailors.** The summary is rewritten deterministically and
  an LLM rewrite is available for the prose the rule engine cannot produce.
- **Comparable choices.** Both variants are scored by the same engine, whenever
  the user asks, so "is the AI rewrite better for this job?" is an evidence-based
  question — and a tailor run costs nothing in scoring time.
- **Edits are contained.** Changing a tailored CV can no longer accidentally
  create a master version (the failure mode that motivated ADR 015).
- **Idempotent and cheap by default.** With no LLM configured, behaviour and cost
  are exactly the deterministic engine's.
- **A broken artifact heals itself.** Re-running the tailor task repairs a
  content-less row instead of reusing it, so a card that shows nothing (or a
  legacy row with no `structured_json`) disappears on the next run — no manual
  SQL, no migration that deletes user data. Until that run it is not listed as a
  CV at all: `GET /api/cv/generated` withholds it and the panel shows the empty
  state, so the job cannot claim a CV that has nothing behind it.

### Negative / Risks

- **ADR 006's "full CV rewrite" rejection is reversed.** Cost and hallucination
  risk are real; the mitigations are: opt-in (the LLM must be explicitly enabled
  in Admin → LLM and an API key stored), no-fabrication prompt, schema
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
- **Provider quirks now live in one file.** `llm_client` special-cases DeepSeek
  (thinking off) by inspecting the base URL. A provider that behaves differently
  again needs that one module updated, and its "thinking" toggle would silently
  stop being applied if the endpoint URL is proxied through a brand that does not
  contain "deepseek". The `llm_empty_content` / `llm_request_failed` log lines
  are the tripwire: they name the model, `finish_reason`, whether
  `reasoning_content` was present, and the token budget.
- **Repair needs a re-run.** A `variant=llm` row left empty by an earlier failed
  rewrite is only repaired when a later run actually produces a rewrite; if the
  LLM stays broken, the empty row remains (it is simply not advertised by the
  task result, which reports only artifacts that exist with content).

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
  `generate_tailored_cv_with_llm`, `_fit_cv_for_prompt`/`LLM_TARGET_PAGES` — the
  tailored-for-the-job prompt, its two-page budget and the valid-JSON trimming of
  an oversized master CV), `app/services/cv_schema.py`
  (`CV_JSON_SCHEMA`, shared with `cv_parser`),
  `workers/tasks/tailor.py` (dual-variant orchestration, in-place repair of a
  content-less artifact via `_has_content`, `_pdf_pages` → `cv_artifact_pages` /
  `llm_rewrite_over_page_budget`)
- `app/services/llm_client.py` (`request_body`, `chat_text`, `chat_json` — the
  only caller of `/chat/completions`; thinking-off toggle, JSON mode, empty
  content treated as failure), used by `cv_tailor`, `cv_parser`, `ats_scorer`
  and the admin probe in `app/routers/app_settings.py`
- `app/routers/cv.py` (`PUT /api/cv/generated/{id}`,
  `GET /api/cv/generated?job_id=` — the list withholds content-less artifacts,
  logging `cv_artifact_without_content_hidden`), `app/routers/applications.py`
  (ownership check on `generated_cv_id`), `app/services/ats_scorer.py`
- `frontend/src/app/shared/cv-panel/` (`hasContent`, `setTailored`),
  `frontend/src/app/components/cv-editor/`
  (deep link removed), `mobile/src/components/cv/CvPanel.tsx`,
  `mobile/src/utils/cv.ts` (`hasContent`),
  `mobile/src/screens/TailoredCvEditorScreen.tsx`
- ADR 002 (data model), ADR 006 (rule-based vs LLM tailoring), ADR 011 (CV
  import/parsing — the LLM structuring pattern reused here), ADR 013 (ATS
  scoring), ADR 015 (per-application workspace)
