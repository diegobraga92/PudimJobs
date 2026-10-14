# ADR 013: ATS Scoring and an ATS-Safe CV Template

## Status

Accepted (2026-10-13)

Amended (2026-10-13): the LLM overlay no longer issues its own HTTP request. The
`_llm_review` call goes through `app/services/llm_client.chat_json` like every
other LLM feature (ADR 016), so it inherits the provider's thinking toggle, JSON
mode and the `llm_empty_content` diagnostic. That mattered here: a thinking-mode
model answered `200 OK` with empty content and the review silently vanished —
the report showed the heuristic blend as if no LLM were configured.

Amended (2026-10-14): the overlay no longer moves the score, and scoring is no
longer a side effect of tailoring. The response reports the deterministic number
as `deterministic_score` (and `score`) plus the LLM's own estimate as
`llm_score`, and `workers/tasks/tailor.py` stores artifacts **unscored** so a
tailor run never spends a scoring budget the user did not ask for.

## Context

Tailoring a CV (ADR 006) and exporting it as a PDF (ADR 011) produce a document
that *looks* good to a human, but applicants are first filtered by Applicant
Tracking Systems (ATS): parsers that read the PDF text layer and score it
against the job description. Two gaps followed from that:

1. The user had no feedback loop — nothing told them *why* a CV would rank
   poorly (missing required skills, unreadable layout, thin content).
2. The default `classic` template is a styled, two-tone layout. Styled layouts
   are exactly what most parsers mangle: multi-column blocks, icon fonts,
   header/footer text, and semantic-free headings.

Requirements: a score a user can act on, a layout designed to be parsed, and no
new mandatory infrastructure (an LLM key must not be required for the feature to
work — same constraint as ADR 006/011).

## Decision

**1. A deterministic ATS scorer with an optional LLM overlay**
(`app/services/ats_scorer.py`, exposed as `POST /api/cv/ats-score`).

The baseline always runs and is composed of four weighted factors:

| Factor | Weight | What it measures |
| ------ | ------ | ---------------- |
| Skill coverage | 0.40 | `match_skills` relevance between required skills (stored `parsed_jd` or parsed on the fly) and the CV's skills + body text |
| Keyword coverage | 0.15 | Fraction of job keywords (description keywords plus significant `job_title` terms) present in the flattened CV text |
| Content completeness | 0.20 | Summary, experience bullets, skills, education, projects, contact details |
| ATS readability | 0.25 | Bullet length, section presence, quantified achievements; returns human-readable warnings |

Factors whose input is unavailable (e.g. no job description) are omitted and the
remaining weights are renormalised, so the endpoint never fails on missing input.
The request may also carry a `job_title`: its significant terms join the keyword
pool (deduped against the description's keywords) and drive a "mirror the job
title" recommendation, so a title-only request still produces a keyword factor.
When `job_id` is given and the body has no `job_title`, the stored job's title is
used as the fallback.
When an OpenAI-compatible endpoint *is* configured, a qualitative review is
requested and reported **beside** the baseline instead of on top of it: the
response carries `llm_score` (the reviewer's own 0-100 estimate, clamped),
`llm_summary` and its extra suggestions, and `method` becomes `"hybrid"`. The
two numbers are never blended — `score`/`deterministic_score` stay reproducible,
so artifacts scored at different moments remain comparable. Any LLM failure,
timeout or out-of-range value simply drops `llm_score` back to `None` and the
report degrades to the pure heuristic score (`method: "heuristic"`).

**2. An opt-in `ats` template** (`app/templates/cv_template_ats.html.j2`)
alongside `classic`: single column, plain sans-serif, no icons/headers/footers,
standard section headings (`Summary`, `Experience`, `Education`, `Skills`,
`Projects`, `Certifications`, `Languages`), and literal text for dates and
bullet markers. The `Skills` section is rendered one labelled line per taxonomy
category (`Languages`, `Frameworks`, `Databases`, `Cloud & DevOps`, `Concepts`,
`Tools`, then `Other`) rather than as one comma-separated keyword dump, on both
templates — the grouping comes from `skill_matcher.group_skills`, so aliases
(`k8s`/`kubernetes`) collapse into a single bucket. Selected per request via
`template=ats` on `POST /api/cv/pdf` and `GET /api/cv/generated/{id}/pdf`;
`classic` remains the default so existing exports are unchanged.

**3. Scores are cached, not recomputed** on `generated_cvs.ats_score`
(int) and `.ats_report` (JSONB, the full factor/recommendation payload) —
migration `0018`. `POST /api/cv/ats-score` writes them only when a
`generated_cv_id` owned by the caller is supplied (audited as
`scored`), and `GET /api/cv/generated/{id}` returns them so the UI can render
the last result without spending an LLM call.

**Scoring is on demand, never a side effect of tailoring.** The Celery tailor
task (ADR 016) stores every artifact with `ats_score`/`ats_report` NULL, so a
generation run spends no scoring time and no artifact shows a number the user
never asked for. The one thing written at generation time is the `llm` variant's
`llm_self_score`, kept inside `ats_report` because a model's opinion of its own
rewrite cannot be recomputed later. Consequently a legacy cached report may
predate `deterministic_score`/`llm_score`; clients must fall back to `score`
when reading an old `ats_report`.

## Consequences

### Positive

- **Actionable feedback** — the response carries per-factor scores, matched and
  missing skills, deterministic recommendations and layout warnings, all
  derivable with zero configuration.
- **Cost-bounded** — the LLM layer is opt-in, runs only when the user asks for a
  score, contributes a number *beside* the deterministic one (never replacing
  it), and never blocks the deterministic result.
- **Deterministic and testable** — the baseline is pure functions
  (`build_report`, `derive_keywords`, `WEIGHTS`), covered by
  `tests/test_ats_scorer.py`, with the endpoint covered end-to-end by
  `tests/test_ats_api.py`.
- **Non-destructive** — `classic` stays the default; the ATS template and the
  score cache are purely additive (migrations `0018`).

### Negative / Risks

- **Heuristic ≠ real ATS** — weights are hand-tuned, not fitted to any vendor's
  parser; a high score is a signal, not a guarantee of passing.
- **Noise in the keyword factor** — with no stored `parsed_jd`, keywords come
  from a frequency fallback (`derive_keywords`), which can rank boilerplate
  above domain terms; the factor is weighted low (0.15) for that reason.
- **Stale caches** — a cached `ats_report` reflects the CV as of scoring time;
  it is recomputed only when the user asks again.
- **Two templates to maintain** — every new `CVStructure` section must be added
  to both `cv_template.html.j2` and `cv_template_ats.html.j2`.

## Alternatives Not Selected

| Option | Reason for Rejection |
| ------ | -------------------- |
| LLM-only scoring | Requires an API key, non-deterministic, no baseline or offline behaviour — the opposite of ADR 006/011's hybrid pattern |
| Third-party ATS scoring API | External dependency, per-call cost and privacy concerns for user CV data |
| Make the ATS template the default | Would silently change every existing/new export and discard the styled layout users already rely on |
| Recompute the score on every page load | Wasted work and LLM cost; a cached `ats_report` is enough for display |

## Where the score is surfaced

The scorer and the two templates are unchanged by ADR 015 (only the UI moved). For
ADR 016, the scorer is now *not* run by the worker at all: tailoring stores both
variants unscored and the same deterministic scorer is applied when the user
clicks *Check score*, so the two variants' scores stay directly comparable and
the master CV is never scored by accident. The AI variant's `llm_self_score` is
still the one number captured at generation time and is preserved across
re-scoring. The report is rendered by
`frontend/src/app/shared/ats-report/` (web) and
`mobile/src/components/cv/AtsReportView.tsx`, inside the per-application
workspace (`/applications/:id`) where the job being scored against is implicit —
previously the user had to pick a job on the `/cv` page. Both render the
deterministic score as the headline and the LLM's own estimate next to it, and
both fall back to `score` when reading a report cached before this amendment.

Since the ADR 016 amendment, `_llm_review` is a thin caller of
`app/services/llm_client.chat_json` (label `LLM ATS review`, 700 tokens), so the
rules that keep it honest live in one place: an empty reply, a transport error or
a non-object reply all degrade to `llm_summary: None` — the deterministic score
is never replaced by a guess, and the reason is logged instead of swallowed.
