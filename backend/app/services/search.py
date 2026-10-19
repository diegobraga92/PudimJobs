"""Keyword-query helpers for the jobs full-text search.

PostgreSQL's ``english`` text-search configuration is a good default, but it
mangles two common technology terms: ``c++`` is tokenized down to ``c`` and
``go`` is treated as a stopword.  Those terms therefore get a dedicated
case-insensitive word-boundary predicate, while everything else keeps using the
indexed ``search_vector`` (which includes tags).
"""

import re

from sqlalchemy import Text, cast, false, func, or_

from app.models.job import Job

# A technology term only counts at a word boundary.  Hyphens are deliberately
# excluded from the boundary for ``go`` so "go-to-market" is not read as the Go
# language, and plus signs stay part of C++.
_SPECIAL_TERM_RE = re.compile(
    r"(?<![a-z0-9-])(c\+\+|cpp|go|golang)(?![a-z0-9-])", re.IGNORECASE
)
_CPP_PATTERN = r"(^|[^a-z0-9+#])(c\+\+|cpp)(?=$|[^a-z0-9+#])"
_GO_PATTERN = r"(^|[^a-z0-9-])(go|golang)(?=$|[^a-z0-9-])"

# Words PostgreSQL's english configuration drops.  If the query is only made of
# these, skipping the FTS predicate is better than ANDing an empty tsquery
# (which would match nothing even when a special term did match).
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _matches_any_field(pattern: str):
    """Case-insensitive regex across the fields a user expects to search."""
    # ``Job.tags`` is JSONB; its text representation is enough for a hit test.
    fields = (Job.title, Job.company, Job.description, cast(Job.tags, Text))
    return or_(*[field.op("~*")(pattern) for field in fields])


def keyword_filters(q: str) -> tuple[list, object | None]:
    """Return SQL predicates plus the tsquery (``None`` when only specials).

    The caller ANDs the predicates onto the list query.  A non-blank query that
    yields no usable predicate gets an always-false clause, preserving the old
    behaviour for stopword-only searches instead of returning every job.
    """
    text = q.strip()
    specials = {match.lower() for match in _SPECIAL_TERM_RE.findall(text)}
    predicates: list = []

    if specials & {"c++", "cpp"}:
        predicates.append(_matches_any_field(_CPP_PATTERN))
    if specials & {"go", "golang"}:
        predicates.append(_matches_any_field(_GO_PATTERN))

    # Feed the remaining words to the indexed search vector.  Special terms are
    # removed so "senior c++" still requires "senior" in the usual way.
    remainder = " ".join(_SPECIAL_TERM_RE.sub(" ", text).split())
    words = [
        word
        for word in re.findall(r"[a-z0-9+#]+", remainder.lower())
        if word not in _STOPWORDS
    ]
    query = func.plainto_tsquery("english", remainder) if words else None
    if query is not None:
        predicates.append(Job.search_vector.op("@@")(query))

    if not predicates:
        predicates.append(false())
    return predicates, query
