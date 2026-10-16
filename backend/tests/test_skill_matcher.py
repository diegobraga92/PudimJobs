"""Unit tests for the skill taxonomy helpers (matching + PDF grouping)."""

from app.services.cv_parser import structure_cv
from app.services.skill_matcher import (
    ADDITIONAL_GROUP,
    canonical_skill,
    group_skills,
    match_skills,
    resolve_skills,
)


def test_canonical_skill_maps_an_alias_to_its_taxonomy_name():
    assert canonical_skill("k8s") == "kubernetes"
    assert canonical_skill("React.js") == "react"
    assert canonical_skill("  python  ") == "python"


def test_group_skills_buckets_by_taxonomy_category_in_taxonomy_order():
    grouped = group_skills(["fastapi", "python", "postgresql", "docker"])

    assert grouped == [
        ("Languages", ["python"]),
        ("Frameworks", ["fastapi"]),
        ("Databases", ["postgresql"]),
        ("Cloud & DevOps", ["docker"]),
    ]


def test_group_skills_keeps_the_given_order_inside_a_group():
    """The tailoring engine already leads with the JD-matched skills."""
    grouped = group_skills(["terraform", "docker", "aws"])

    assert grouped == [("Cloud & DevOps", ["terraform", "docker", "aws"])]


def test_group_skills_uses_the_taxonomy_for_aliases_and_drops_duplicates():
    grouped = group_skills(["k8s", "kubernetes", "K8S"])

    # All three spell the same skill: the first spelling wins, once.
    assert grouped == [("Cloud & DevOps", ["k8s"])]


def test_group_skills_sends_unknown_skills_to_a_final_additional_bucket():
    """The leftover bucket is labelled "Additional", never the off-putting "Other"."""
    grouped = group_skills(["python", "stakeholder management", "python"])

    assert ADDITIONAL_GROUP == "Additional"
    assert grouped == [
        ("Languages", ["python"]),
        (ADDITIONAL_GROUP, ["stakeholder management"]),
    ]


def test_group_skills_ignores_blank_and_non_string_entries():
    assert group_skills(["", "   ", None, 7]) == []  # type: ignore[list-item]
    assert group_skills([]) == []


def test_canonical_skill_maps_the_framework_and_cloud_aliases():
    assert canonical_skill("RoR") == "rails"
    assert canonical_skill("CDK") == "aws cdk"
    assert canonical_skill("Test-Driven Development") == "test driven development"


def test_group_skills_places_common_frameworks_and_cloud_tools():
    """These are real skills, not leftovers: they must not fall to "Additional"."""
    grouped = dict(
        group_skills(
            [
                "Qt",
                "Boost",
                "Protobuf",
                "gRPC",
                "Apache Thrift",
                "Tauri",
                "RoR",
                "Celery",
                "n8n",
                "Nginx",
                "Artifactory",
                "CDK",
                "OpenSSL",
                "TLS",
            ]
        )
    )

    assert grouped == {
        "Frameworks": [
            "Qt",
            "Boost",
            "Protobuf",
            "gRPC",
            "Apache Thrift",
            "Tauri",
            "RoR",
            "Celery",
            "n8n",
        ],
        "Cloud & DevOps": ["Nginx", "Artifactory", "CDK", "OpenSSL", "TLS"],
    }


def test_group_skills_places_a_parsed_labelled_section_without_leftovers():
    """End-to-end guard for the reported bug.

    A labelled skills section used to leave its own label words ("Frameworks",
    "Cloud", "DevOps") plus every multi-word/slashed fragment ("Apache", "Thrift",
    "CI", "CD") in the "Additional" bucket.
    """
    cv = structure_cv(
        "SKILLS\n"
        "Frameworks: Flask, Qt, Apache Thrift\n"
        "Cloud & DevOps: AWS, CI/CD, Nginx\n"
        "Concepts: Test-Driven Development\n"
    )
    grouped = dict(group_skills(cv.skills))

    assert grouped == {
        "Frameworks": ["Flask", "Qt", "Apache Thrift"],
        "Cloud & DevOps": ["AWS", "CI/CD", "Nginx"],
        "Concepts": ["Test-Driven Development"],
    }
    assert ADDITIONAL_GROUP not in grouped


def test_resolve_skills_walks_its_ladder():
    # Exact taxonomy name or alias, a compound whose parts are all known, and the
    # longest known name inside a longer entry.
    assert resolve_skills("K8S") == ["kubernetes"]
    assert resolve_skills("JavaScript/TypeScript") == ["javascript", "typescript"]
    assert resolve_skills("Google BigQuery") == ["bigquery"]

    # Unknown entries come back untouched: nothing is silently dropped from a CV.
    assert resolve_skills("stakeholder management") == ["stakeholder management"]


def test_group_skills_places_compound_entries_by_their_parts():
    """A compound names two skills, and its group is the one they agree on."""
    grouped = dict(
        group_skills(
            [
                "JavaScript/TypeScript",
                "Protobuf/gRPC",
                "Google BigQuery",
                "OpenSSL/TLS",
                "Agile/Scrum",
                "Test-Driven Development (TDD)",
            ]
        )
    )

    assert grouped == {
        "Languages": ["JavaScript/TypeScript"],
        "Frameworks": ["Protobuf/gRPC"],
        "Databases": ["Google BigQuery"],
        "Cloud & DevOps": ["OpenSSL/TLS"],
        "Concepts": ["Agile/Scrum", "Test-Driven Development (TDD)"],
    }


def test_group_skills_sends_a_compound_whose_parts_disagree_to_additional():
    # "AWS/PostgreSQL" is a cloud skill and a database at once, so any group would
    # be a coin flip; the taxonomy says so by leaving it in the leftover bucket.
    grouped = group_skills(["AWS/PostgreSQL"])

    assert grouped == [(ADDITIONAL_GROUP, ["AWS/PostgreSQL"])]


def test_group_skills_drops_a_repeat_of_the_same_resolved_skills():
    # Same resolved set, first spelling wins...
    assert group_skills(["TypeScript", "typescript"]) == [("Languages", ["TypeScript"])]
    # ...but a compound keeps its own entry: it names a skill the other does not,
    # and the CV's own spelling is never rewritten.
    assert group_skills(["JavaScript/TypeScript", "TypeScript"]) == [
        ("Languages", ["JavaScript/TypeScript", "TypeScript"])
    ]


def test_match_skills_credits_a_compound_cv_entry():
    """A CV that writes "JavaScript/TypeScript" has both skills."""
    result = match_skills(["TypeScript", "Rust"], ["JavaScript/TypeScript"])

    assert result["matched"] == ["TypeScript"]
    assert result["missing"] == ["Rust"]
    assert result["relevance"] == 0.5


def test_group_skills_places_the_reported_compound_block_without_leftovers():
    """End-to-end guard for the reported bug.

    A skills section whose later lines carry compound labels ("Frameworks & Tools:",
    "Databases & Analytics:", "Systems & Tools:") used to render as one "Additional"
    line holding the label text glued to the first value, the "Additional"/
    "Methodologies" words themselves, and "Test-Driven Development (TDD" truncated.
    """
    cv = structure_cv(
        "SKILLS\n"
        "Languages: C++, Rust, Python, Golang, C, C#, Ruby\n"
        "Frameworks: Boost, Flask, Apache Thrift, Tauri, RoR, Celery, n8n\n"
        "Databases: SQL Server, MongoDB, Redis, SQLite\n"
        "Cloud & DevOps: AWS, Azure, Docker, Jenkins, CI/CD, Nginx, Terraform, AWS CDK\n"
        "Concepts: Kanban, Microservices\n"
        "Tools: Windows, macOS, Git, Confluence, JIRA\n"
        "Additional: JavaScript/TypeScript\n"
        "Frameworks & Tools: Qt, Protobuf/gRPC\n"
        "Databases & Analytics: PostgreSQL, Google BigQuery\n"
        "Systems & Tools: Linux, OpenSSL/TLS\n"
        "Methodologies: Agile/Scrum, Test-Driven Development (TDD)\n"
    )
    grouped = group_skills(cv.skills)

    assert grouped == [
        (
            "Languages",
            ["C++", "Rust", "Python", "Golang", "C", "C#", "Ruby", "JavaScript/TypeScript"],
        ),
        (
            "Frameworks",
            [
                "Boost",
                "Flask",
                "Apache Thrift",
                "Tauri",
                "RoR",
                "Celery",
                "n8n",
                "Qt",
                "Protobuf/gRPC",
            ],
        ),
        (
            "Databases",
            ["SQL Server", "MongoDB", "Redis", "SQLite", "PostgreSQL", "Google BigQuery"],
        ),
        (
            "Cloud & DevOps",
            [
                "AWS",
                "Azure",
                "Docker",
                "Jenkins",
                "CI/CD",
                "Nginx",
                "Terraform",
                "AWS CDK",
                "OpenSSL/TLS",
            ],
        ),
        ("Concepts", ["Kanban", "Microservices", "Agile/Scrum", "Test-Driven Development (TDD)"]),
        ("Tools", ["Windows", "macOS", "Git", "Confluence", "JIRA", "Linux"]),
    ]


def test_group_skills_keeps_the_reported_blocks_acronym_intact():
    """The truncated "Test-Driven Development (TDD" must not come back."""
    cv = structure_cv("SKILLS\nMethodologies: Test-Driven Development (TDD)\n")

    assert cv.skills == ["Test-Driven Development (TDD)"]
    assert group_skills(cv.skills) == [("Concepts", ["Test-Driven Development (TDD)"])]
