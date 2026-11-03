"""Unit tests for the CV field-order repair helpers (no DB writes)."""

from scripts.repair_cv_fields import is_inverted_role, swap_inverted_experience

# The shape the old parser produced for a CV whose headers read
# "Company — Title": the two names stored the wrong way round.
INVERTED_CV = {
    "summary": "Backend engineer",
    "experience": [
        {
            "title": "Axcient",
            "company": "Senior Software Engineer (Remote)",
            "start_date": "2022-07",
            "end_date": "2025-10",
            "bullets": ["Built a cross-platform backup agent in C++ and Rust"],
        },
        {
            "title": "Embraer S.A.",
            "company": "Product Development Engineer (São Paulo, Brazil)",
            "start_date": "2013-06",
            "end_date": "2021-05",
            "bullets": ["Modelled aircraft systems"],
        },
    ],
}


def test_is_inverted_role_flags_the_company_first_signature():
    assert is_inverted_role(INVERTED_CV["experience"][0])
    assert is_inverted_role(INVERTED_CV["experience"][1])


def test_is_inverted_role_accepts_a_role_that_was_parsed_correctly():
    assert not is_inverted_role(
        {
            "title": "Senior Software Engineer (Remote)",
            "company": "Axcient",
        }
    )
    # A title the vocabulary does not know is still a title when the other side
    # names no job either: nothing to repair.
    assert not is_inverted_role({"title": "Founding Team", "company": "Axcient"})
    # Same text on both sides is a parse failure, not a swap.
    assert not is_inverted_role({"title": "Acme", "company": "Acme"})
    # An employer that merely *contains* a job word is not an inverted title.
    assert not is_inverted_role({"title": "Sales", "company": "Engineer Solutions Ltda"})
    assert not is_inverted_role({"title": "", "company": "Senior Software Engineer"})


def test_swap_inverted_experience_repairs_only_the_two_names():
    structure, swapped, samples = swap_inverted_experience(INVERTED_CV)

    assert swapped == 2
    assert samples[0] == ("Axcient", "Senior Software Engineer (Remote)")
    first = structure["experience"][0]
    assert (first["title"], first["company"]) == ("Senior Software Engineer (Remote)", "Axcient")
    # Everything else is copied verbatim.
    assert first["start_date"] == "2022-07"
    assert first["end_date"] == "2025-10"
    assert first["bullets"] == ["Built a cross-platform backup agent in C++ and Rust"]
    # The caller decides whether to persist, so the input must survive untouched.
    assert INVERTED_CV["experience"][0]["title"] == "Axcient"
    assert structure["summary"] == "Backend engineer"


def test_swap_inverted_experience_leaves_a_correct_cv_alone():
    correct = {
        "experience": [
            {"title": "Senior Software Engineer", "company": "Axcient"},
            {"title": "Product Development Engineer", "company": "Embraer S.A."},
        ]
    }
    structure, swapped, samples = swap_inverted_experience(correct)
    assert (swapped, samples) == (0, [])
    assert structure is correct


def test_swap_inverted_experience_tolerates_malformed_data():
    assert swap_inverted_experience({}) == ({}, 0, [])
    assert swap_inverted_experience({"experience": "nope"}) == (
        {"experience": "nope"},
        0,
        [],
    )

    structure, swapped, samples = swap_inverted_experience(
        {"experience": ["not-a-role", {"title": "Axcient"}, INVERTED_CV["experience"][0]]}
    )
    assert swapped == 1
    assert len(samples) == 1
    assert structure["experience"][0] == "not-a-role"
    assert structure["experience"][1] == {"title": "Axcient"}
    assert structure["experience"][2]["company"] == "Axcient"
