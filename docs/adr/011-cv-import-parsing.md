# ADR 011 — CV Import: PDF/DOCX Parsing

Status: accepted
Date: 2026-08-14

## Context

The master CV editor requires users to type every section by hand. Most users
already have a resume as a PDF or DOCX, so the natural onboarding step is to
upload that file and get the editor pre-filled for review.

The job-description side already has a parsing precedent (ADR 006): a
deterministic, testable core (regex + taxonomy) with an opt-in LLM polish
layer. CV parsing is harder than JD parsing — resume layouts vary wildly — but
the same cost/quality trade-off applies.

## Decision

Add `POST /api/cv/parse`: an authenticated multipart upload of a `.pdf` or
`.docx` (max 5 MB) that returns a `CVStructure` **without persisting anything**.
The frontend pre-fills the editor, the user reviews/edits, and saves via the
existing `POST /api/cv` (which keeps the audit trail and versioning).

Extraction and structuring live in a new service `app/services/cv_parser.py`:

1. **Text extraction is deterministic**: `pypdf` for PDFs, `python-docx` for
   DOCX (paragraphs + table cells).
2. **Structuring is hybrid, mirroring ADR 006**:
   - A rule-based heuristic core (`structure_cv`) always runs: whole-line
     section-heading detection (summary/experience/education/skills/projects),
     title/company/date extraction with per-line date-range handling, bullet
     grouping, skill splitting, and project/link capture. Output is always
     validated against the `CVStructure` schema.
   - An optional LLM (`structure_cv_with_llm`) is tried first **only when** an
     OpenAI-compatible API key is configured (`llm_config` DB row or env
     fallback). It returns strict JSON validated against `CVStructure`; any
     failure (network, malformed JSON, invalid shape) degrades gracefully to
     the rule-based result.
3. **The response is never auto-saved**: matching the tailoring flow, the user
   is always the reviewer before a new `master_cv` version is created.

## Alternatives considered

- **LLM-only parsing** — best quality on messy CVs but requires an API key,
  adds latency/cost, and is non-deterministic; no baseline when unconfigured.
- **Frontend (browser) parsing** — no server round-trip, but no existing PDF
  library in the Angular bundle, weaker DOCX support, and parsing logic would
  be duplicated/untestable against the backend test suite.
- **Auto-save the parsed result as a new version** — convenient but skips the
  review step that every other CV-writing path in the app enforces.

## Consequences

- CV import works out of the box with zero configuration (rule-based path);
  enabling the LLM simply improves fidelity for free-form layouts.
- Parsing is server-side and fully unit-testable (see
  `tests/test_cv_parser.py`); the API endpoint is covered by
  `tests/test_cv_parse_api.py`.
- The heuristic parser is intentionally conservative: it only fills what it
  can identify confidently, so users always correct or extend the draft.
- Two new runtime dependencies: `pypdf` and `python-docx`.
- The upload is rate-limited like other API endpoints (`rate_limit_api`) and
  size-capped (5 MB), keeping LLM costs bounded per request.
