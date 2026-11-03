"""Dry-run-first repair for CVs stored with `title` and `company` swapped.

A CV whose role headers put the employer first ("Acme — Senior Software
Engineer") used to be parsed by position, so every role landed in the master CV
with its two name fields inverted. The preview hides it ("Acme / Jul 2022 —
Oct 2025 / Senior Software Engineer" reads naturally) while the exports, the
rule variant and the role matching in tailoring all carry the swap. The parser
now reads the header by meaning (ADR 028); this script repairs what it already
stored, and only *writes* with ``--apply``.

A repaired CV loses the tailored artifacts derived from it: they were rendered
from the inverted structure, and the tailor task reuses an existing artifact for
the same master CV/job pair, so keeping them would keep serving the swap. An
application that pointed at one keeps its record but loses the attached CV
(`generated_cv_id` is `ON DELETE SET NULL`), so re-tailor and relink afterwards
if that matters.

Examples::

    # What would change, for one user, without touching anything.
    python scripts/repair_cv_fields.py --user-email me@example.com

    # Apply it, then re-tailor: the artifacts are dropped with the swap.
    python scripts/repair_cv_fields.py --user-email me@example.com --apply

    # Keep the tailored PDFs (they still show the old field order).
    python scripts/repair_cv_fields.py --user-email me@example.com --apply \
        --keep-artifacts

    # Also repair superseded versions, not only the current CV.
    python scripts/repair_cv_fields.py --all-versions

Remove ``--apply`` to preview every CV, the swapped role count and a sample of
the pairs. Only the unambiguous signature is repaired — a stored title that
names no job while the stored employer ends in one — so a CV that was parsed
correctly is never touched.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

# Allow running as `python scripts/repair_cv_fields.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app.database import async_session_factory  # noqa: E402
from app.models import Application, GeneratedCV, MasterCV, User  # noqa: E402
from app.services.cv_parser import is_role_word, role_title_score  # noqa: E402
from app.services.text_norm import fold_text, fold_words  # noqa: E402

_BRACKETED_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")


def _head_word(part: str) -> str:
    """The last word of a title/company, ignoring a trailing location or note."""
    words = fold_words(_BRACKETED_RE.sub(" ", part))
    return words[-1] if words else ""


def is_inverted_role(role: dict) -> bool:
    """Whether one stored role has ``title`` and ``company`` the wrong way round.

    Only the unambiguous signature is repaired: the stored title names no job at
    all, while the stored employer *ends* in a job title ("Axcient" /
    "Senior Software Engineer (Remote)"). Requiring the head word, not just any
    word, keeps a correctly stored "Sales" / "Engineer Solutions Ltda" out of the
    fix.
    """
    title = str(role.get("title") or "")
    company = str(role.get("company") or "")
    if not title or not company or fold_text(title) == fold_text(company):
        return False
    return role_title_score(title) == 0 and is_role_word(_head_word(company))


def swap_inverted_experience(structure: dict) -> tuple[dict, int, list[tuple[str, str]]]:
    """Swap the inverted roles of one CV; return ``(structure, count, samples)``.

    Only the two names move: dates, bullets and every other field stay exactly as
    stored, and the input is never mutated. ``samples`` holds the original
    ``(title, company)`` pairs, so a dry run can show what it would change.
    """
    roles = structure.get("experience")
    if not isinstance(roles, list):
        return structure, 0, []
    repaired: list[dict] = []
    samples: list[tuple[str, str]] = []
    for role in roles:
        if not isinstance(role, dict) or not is_inverted_role(role):
            repaired.append(role)
            continue
        title = str(role.get("title") or "")
        company = str(role.get("company") or "")
        samples.append((title, company))
        repaired.append({**role, "title": company, "company": title})
    if not samples:
        return structure, 0, []
    return {**structure, "experience": repaired}, len(samples), samples


async def _repair(args: argparse.Namespace) -> int:
    async with async_session_factory() as session:
        query = select(MasterCV)
        if args.user_email:
            query = query.join(User, User.id == MasterCV.user_id).where(
                User.email == args.user_email
            )
        if args.cv_id:
            query = query.where(MasterCV.id == args.cv_id)
        if not args.all_versions:
            query = query.where(MasterCV.is_current.is_(True))
        query = query.order_by(MasterCV.created_at)
        if args.limit:
            query = query.limit(args.limit)
        cvs = list((await session.execute(query)).scalars())

        print(f"Scanned {len(cvs)} CV version(s).")
        repaired_cvs = 0
        repaired_roles = 0
        dropped_artifacts = 0
        for cv in cvs:
            fixed, swapped, samples = swap_inverted_experience(cv.structured_json or {})
            if not swapped:
                continue
            repaired_cvs += 1
            repaired_roles += swapped
            print(f"\n  CV {cv.id} (v{cv.version}, {cv.label!r}): {swapped} role(s) inverted")
            for title, company in samples[:5]:
                print(f"    title={title!r} company={company!r}")
            if len(samples) > 5:
                print(f"    … and {len(samples) - 5} more")
            if not args.apply:
                continue

            cv.structured_json = fixed
            if not args.keep_artifacts:
                dropped_artifacts += await _drop_artifacts(session, cv.id)

        print(
            f"\n{repaired_cvs} CV version(s), {repaired_roles} role(s) "
            f"{'repaired' if args.apply else 'to repair'}."
        )
        if args.apply:
            await session.commit()
            print(f"Changes committed; {dropped_artifacts} tailored artifact(s) removed.")
        else:
            await session.rollback()
            print("Dry run only; pass --apply to write these changes.")
    return 0


async def _drop_artifacts(session, cv_id) -> int:
    """Delete the tailored artifacts built from one CV; return how many.

    They were rendered from the inverted structure and the tailor task reuses an
    existing artifact for the same (CV, job) pair, so a stale copy would keep the
    swap in front of the user. An application that pointed at one keeps its record
    but loses the link (`generated_cv_id` is `ON DELETE SET NULL`), which is
    reported so the operator can re-tailor and relink.
    """
    artifacts = list(
        (
            await session.execute(
                select(GeneratedCV.id).where(GeneratedCV.source_master_cv_id == cv_id)
            )
        ).scalars()
    )
    if not artifacts:
        return 0
    # Counted before the delete: afterwards the rows are gone in this transaction.
    linked = (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(Application.generated_cv_id.in_(artifacts))
        )
    ).scalar() or 0
    await session.execute(delete(GeneratedCV).where(GeneratedCV.id.in_(artifacts)))
    print(f"    dropped {len(artifacts)} tailored artifact(s); re-tailor to rebuild them")
    if linked:
        print(f"    {linked} application(s) lose their attached CV; re-tailor and relink")
    return len(artifacts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-email", default=None, help="repair one user's CVs only")
    parser.add_argument("--cv-id", default=None, help="repair a single master_cv id only")
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="include superseded versions (default: the current CV only)",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="keep the tailored artifacts derived from a repaired CV",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap the CVs scanned")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the changes (without it the script only reports)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_repair(args))


if __name__ == "__main__":
    raise SystemExit(main())
