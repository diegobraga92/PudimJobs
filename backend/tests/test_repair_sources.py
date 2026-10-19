"""Unit tests for the source/job repair helpers (no DB writes)."""

from types import SimpleNamespace

import pytest
from scripts.repair_sources import (
    _feed_page_url,
    _source_matches,
    apply_detail_fields,
    apply_listing_fields,
    job_haystack,
    needs_detail_refresh,
    parse_config_assignments,
    split_company_title,
)


def test_split_company_title_handles_board_shaped_titles():
    assert split_company_title("Acme Corp: Senior Rust Engineer") == (
        "Senior Rust Engineer",
        "Acme Corp",
    )
    assert split_company_title("No separator here") is None
    assert split_company_title("") is None


def test_parse_config_assignments_keeps_json_types():
    parsed = parse_config_assignments(
        [
            "company_from_title=true",
            "max_results=25",
            "exclude_pattern=\\bexpirada\\b",
            "tags=[\"rust\", \"remote\"]",
        ]
    )

    assert parsed == {
        "company_from_title": True,
        "max_results": 25,
        "exclude_pattern": "\\bexpirada\\b",
        "tags": ["rust", "remote"],
    }


def test_parse_config_assignments_rejects_a_bare_key():
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_config_assignments(["company_from_title"])


def test_feed_page_url_keeps_page_one_and_pages_wordpress_feeds():
    assert _feed_page_url("https://jobspresso.co/jobs/feed/", 1) == (
        "https://jobspresso.co/jobs/feed/"
    )
    assert _feed_page_url("https://jobspresso.co/jobs/feed/", 3) == (
        "https://jobspresso.co/jobs/feed/?paged=3"
    )
    assert _feed_page_url("https://board.example/feed?type=jobs", 2) == (
        "https://board.example/feed?type=jobs&paged=2"
    )


def test_needs_detail_refresh_targets_incomplete_rows():
    complete = SimpleNamespace(
        title="Rust Engineer",
        company="Acme",
        description="x" * 100,
        posted_date="2026-10-01",
        tags=["rust"],
    )
    bare = SimpleNamespace(
        title="Rust Engineer",
        company="Unknown",
        description=None,
        posted_date=None,
        tags=[],
    )
    assert needs_detail_refresh(complete) is False
    assert needs_detail_refresh(bare) is True


def test_apply_detail_fields_fills_only_missing_data():
    job = SimpleNamespace(
        title="Rust Engineer",
        company="Unknown",
        description=None,
        posted_date=None,
        tags=[],
    )
    candidate = SimpleNamespace(
        title="Rust Engineer",
        company="Acme",
        description="A much longer detail description.",
        posted_date="2026-10-01",
        tags=["rust", "remote"],
    )
    assert apply_detail_fields(job, candidate) == [
        "company",
        "description",
        "posted_date",
        "tags",
    ]
    assert job.company == "Acme"
    assert job.tags == ["rust", "remote"]
    # A short card snippet never replaces a longer stored description.
    job.description = "A stored description that is already long enough."
    assert apply_detail_fields(job, candidate) == []


def test_apply_listing_fields_updates_board_shaped_rows():
    job = SimpleNamespace(
        title="Acme: Rust Engineer",
        company="We Work Remotely",
        description=None,
        posted_date=None,
        tags=[],
    )
    item = {
        "title": "Rust Engineer",
        "company": "Acme",
        "description": "<p>Build Rust.</p>",
        "posted_date": "2026-10-01",
        "tags": ["Remote"],
    }
    assert apply_listing_fields(job, item) == [
        "title",
        "company",
        "description",
        "posted_date",
        "tags",
    ]
    assert job.company == "Acme"


def test_job_haystack_matches_stale_labels_in_any_field():
    job = SimpleNamespace(
        title="Rust Engineer",
        company="Acme",
        description="Vaga expirada",
        url="https://board.example/jobs/1",
        tags=["rust"],
    )
    assert "expirada" in job_haystack(job)
    assert "https://board.example/jobs/1" in job_haystack(job)


def test_source_matches_url_or_name_case_insensitively():
    source = SimpleNamespace(
        url="https://weworkremotely.com/remote-jobs.rss",
        name="We Work Remotely",
    )
    assert _source_matches(source, ["WEWORKREMOTELY"], [])
    assert _source_matches(source, [], ["we work"])
    assert not _source_matches(source, ["remoteyeah"], ["toughbyte"])
