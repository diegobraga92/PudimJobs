"""Accent- and case-insensitive folding, shared by the CV services.

A parsed CV, an LLM reply and a stored master CV rarely agree on accents,
punctuation or case: the same employer is ``Embraer S.A.`` in one place and
``embraer sa`` in another, and ``São Paulo`` is ``Sao Paulo`` as soon as
something round-trips through a PDF. Every comparison folds both sides first.

The rule matches ``scrapers.utils.fold_text``, already used to match job
locations, so the whole app folds text the same way.
"""

import re
import unicodedata

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def fold_text(value: object) -> str:
    """Case- and accent-insensitive text: ``São Paulo`` -> ``sao paulo``."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return folded.casefold().strip()


def fold_words(value: object) -> list[str]:
    """The folded words of ``value``, every run of punctuation collapsed."""
    return _NON_WORD_RE.sub(" ", fold_text(value)).strip().split()
