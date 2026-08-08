# ADR 006: Rule-Based vs LLM CV Tailoring

## Status

Accepted (2026-08-08)

## Context

The CV tailoring feature must produce a job-specific CV from the master CV and
a job description. Two fundamentally different approaches exist:

- **Rule-based**: deterministically select/reorder relevant CV sections by
  matching JD skills against CV content and annotations. Fast, free,
  predictable.
- **LLM-based**: ask a language model to rephrase bullets using the JD's
  language. Fluent, natural-sounding, but costs money per generation, adds
  latency, and is non-deterministic.

## Decision

### Default to a rule-based engine; LLM as an opt-in enhancement

1. `cv_tailor.tailor_cv()` implements the deterministic pipeline:
   - Parse the JD into required skills (spaCy + taxonomy).
   - Score each experience/project block against the JD skills (content match
     plus user/auto annotations).
   - Keep only relevant blocks, ordered by relevance.
   - Reorder the skills list (matched first).
2. `cv_tailor.enhance_with_llm()` rephrases the selected bullets via an
   OpenAI-compatible API, **only when** `TAILORING_LLM_ENABLED=true` and an API
   key is configured. Any failure degrades gracefully to the original bullets.
3. The tailored result is stored as a new (non-current) `master_cv` version
   plus a rendered PDF in `generated_cvs`; the user reviews and edits before
   it becomes current.

### Why this split

- The rule-based path is deterministic and fully testable (see
  `tests/test_cv_tailor.py`), zero marginal cost, and sub-second.
- The LLM is a polish layer on top of a sound selection, not the selection
  itself — the "which bullets are relevant" decision stays deterministic and
  auditable.
- Feature-flagging keeps the default deployment free and predictable.

## Consequences

### Positive

- Deterministic, testable core with cheap default path.
- LLM enhancement available without architectural change.
- Users can always review/edit the generated version.

### Negative / Risks

- Rule-based output can sound formulaic compared to a human/LLM rewrite.
- LLM path has cost/latency/quality variance; mitigated by rate limits
  (max 5 bullet rephrases) and graceful degradation.
- The taxonomy-based skill extraction may miss niche/evolving skills
  (mitigation: `skills_taxonomy.json` is a versioned data file, easy to grow).

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| LLM-only generation | Cost, latency, non-determinism, no baseline without API keys |
| Hand-written per-job templates | Not scalable; defeats the "tailor at scale" goal |
| Full CV rewrite by LLM | Highest cost; risk of hallucinated experience — unacceptable |
