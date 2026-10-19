"""Unit tests for the source/job repair helpers (no DB writes)."""

from types import SimpleNamespace

import pytest
from scripts.repair_sources import (
    _source_matches,
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


def test_source_matches_url_or_name_case_insensitively():
    source = SimpleNamespace(
        url="https://weworkremotely.com/remote-jobs.rss",
        name="We Work Remotely",
    )
    assert _source_matches(source, ["WEWORKREMOTELY"], [])
    assert _source_matches(source, [], ["we work"])
    assert not _source_matches(source, ["remoteyeah"], ["toughbyte"])
