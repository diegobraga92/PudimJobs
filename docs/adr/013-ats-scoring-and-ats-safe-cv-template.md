# ADR 013: ATS Scoring and an ATS-Safe CV Template

## Status

Accepted (2026-10-13)

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
requested and blended as `0.7 * heuristic + 0.3 * llm` (`method: "hybrid"`); any
LLM failure, timeout or out-of-range value silently degrades to the pure
heuristic score (`method: "heuristic"`).

**2. An opt-in `ats` template** (`app/templates/cv_template_ats.html.j2`)
alongside `classic`: single column, plain sans-serif, no icons/headers/footers,
standard section headings (`Summary`, `Experience`, `Education`, `Skills`,
`Projects`, `Certifications`, `Languages`), and literal text for dates and
bullet markers. Selected per request via `template=ats` on
`POST /api/cv/pdf` and `GET /api/cv/generated/{id}/pdf`; `classic` remains the
default so existing exports are unchanged.

**3. Scores are cached, not recomputed** on `generated_cvs.ats_score`
(int) and `.ats_report` (JSONB, the full factor/recommendation payload) —
migration `0018`. `POST /api/cv/ats-score` writes them only when a
`generated_cv_id` owned by the caller is supplied (audited as
`scored`), and `GET /api/cv/generated/{id}` returns them so the UI can render
the last result without spending an LLM call.

## Consequences

### Positive

- **Actionable feedback** — the response carries per-factor scores, matched and
  missing skills, deterministic recommendations and layout warnings, all
  derivable with zero configuration.
- **Cost-bounded** — the LLM layer is opt-in, capped at a 30% score influence,
  and never blocks the deterministic result.
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
