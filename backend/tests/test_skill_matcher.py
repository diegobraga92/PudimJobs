"""Unit tests for the skill taxonomy helpers (matching + PDF grouping)."""

from app.services.skill_matcher import OTHER_GROUP, canonical_skill, group_skills


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


def test_group_skills_sends_unknown_skills_to_a_final_other_bucket():
    grouped = group_skills(["python", "stakeholder management", "python"])

    assert grouped == [
        ("Languages", ["python"]),
        (OTHER_GROUP, ["stakeholder management"]),
    ]


def test_group_skills_ignores_blank_and_non_string_entries():
    assert group_skills(["", "   ", None, 7]) == []  # type: ignore[list-item]
    assert group_skills([]) == []
