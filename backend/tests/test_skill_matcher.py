"""Unit tests for the skill taxonomy helpers (matching + PDF grouping)."""

from app.services.cv_parser import structure_cv
from app.services.skill_matcher import ADDITIONAL_GROUP, canonical_skill, group_skills


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
