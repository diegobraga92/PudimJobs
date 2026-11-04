"""Recruiter-safe CV export filenames (ADR 030).

The name a recruiter sees in an attachment list is part of the document. A file
called ``tailored-cv-8f3a1c2e-9b7d-4e21-....pdf`` tells the reader two things it
should not: that a machine assembled it, and nothing about who it belongs to.
The name here follows the order a person would give it — who, which document,
which role:

    Ada-Lovelace-CV-Backend-Engineer.pdf

The role is the only segment that legitimately differs between two CVs of the
same person, so it is what keeps a second download from becoming
``Ada-Lovelace-CV (1).pdf``. The artifact UUID stays an internal key and never
reaches a filename.

Everything here is deliberately ASCII and hyphen-joined: an accent turns into
``%C3%A9`` or ``_`` depending on the upload form, and spaces become ``%20``,
while every mail client, ATS upload widget and filesystem takes ``[A-Za-z0-9-]``
unchanged. The output is used verbatim inside a ``Content-Disposition`` header,
so it must never carry a quote or a newline — the slug rule guarantees that.
"""

import re
import unicodedata

from app.services.cv_labels import DEFAULT_LANGUAGE

# Capped on word boundaries: long enough for a full legal name, short enough
# that name + document + role stay far inside the 255-byte limit every
# filesystem (and Outlook's attachment path) shares. The role is the variable
# part of the name, so it gets the smaller budget.
_MAX_NAME_CHARS = 48
_MAX_ROLE_CHARS = 40

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")
# "(Remote)", "[Contract]": parentheticals are detail, not identity.
_BRACKETED_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")

# A parser can read a section heading as the candidate's name. Joining it to the
# document type would print "Curriculum-Vitae-CV.pdf".
_JUNK_NAMES = frozenset({"cv", "curriculum", "curriculum-vitae", "curriculo", "resume"})


def _ascii(value: object) -> str:
    """Accent-free text that keeps its capitalisation: ``José`` -> ``Jose``.

    ``text_norm.fold_text`` folds the case as well, which is right for comparing
    two CVs and wrong for a file a person reads.
    """
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def slug(value: object, max_chars: int) -> str:
    """A safe token: ``Backend Engineer (Remote)`` -> ``Backend-Engineer``."""
    words = _NON_ALNUM_RE.sub(" ", _BRACKETED_RE.sub(" ", _ascii(value))).split()
    if not words:
        return ""
    # A single over-long word (a pasted URL, a run-together headline) is cut
    # rather than dropped: an empty segment would silently lose the name.
    kept = [words[0][:max_chars]]
    length = len(kept[0])
    for word in words[1:]:
        if length + 1 + len(word) > max_chars:
            break
        kept.append(word)
        length += 1 + len(word)
    return "-".join(kept).strip("-")


def cv_stem(
    *,
    full_name: object = "",
    account_name: object = "",
    job_title: object = "",
) -> str:
    """The recruiter-facing base name: ``Ada-Lovelace-CV-Backend-Engineer``.

    ``full_name`` is the name the document itself prints; ``account_name`` is the
    email-derived fallback the renderers already use for the header, so the file
    and the page never disagree. With neither, the name degrades to ``CV``.
    """
    name = slug(full_name, _MAX_NAME_CHARS) or slug(account_name, _MAX_NAME_CHARS)
    parts = [] if not name or name.casefold() in _JUNK_NAMES else [name]
    parts.append("CV")
    role = slug(job_title, _MAX_ROLE_CHARS)
    if role:
        parts.append(role)
    return "-".join(parts)


def export_filename(
    stem: str,
    *,
    fmt: str = "pdf",
    template: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """``stem`` + layout/language marker + extension: ``Ada-Lovelace-CV-ATS-pt-br.pdf``.

    The classic/ATS split is a PDF-styling concern, so DOCX — one plain layout —
    never carries the marker (ADR 017).
    """
    parts = [stem]
    if fmt == "pdf" and template == "ats":
        parts.append("ATS")
    if language != DEFAULT_LANGUAGE:
        parts.append(language.lower())
    return "-".join(parts) + f".{fmt}"


def tailored_filename(
    *,
    full_name: object = "",
    account_name: object = "",
    job_title: object = "",
    fmt: str = "pdf",
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """Download name for a tailored artifact — never its UUID (ADR 030)."""
    return export_filename(
        cv_stem(full_name=full_name, account_name=account_name, job_title=job_title),
        fmt=fmt,
        language=language,
    )
