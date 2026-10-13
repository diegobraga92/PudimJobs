"""Unit tests for the PDF/DOCX CV parser (extraction + structuring)."""

import pytest

from app.schemas.master_cv import CVStructure
from app.services.cv_parser import (
    InvalidFileError,
    UnsupportedFileTypeError,
    extract_text,
    extract_text_from_docx,
    extract_text_from_odt,
    extract_text_from_pdf,
    parse_cv_file,
    structure_cv,
    structure_cv_with_llm,
)
from app.services.llm_config import LlmRuntimeConfig
from tests.helpers import make_docx, make_odt, make_pdf

SAMPLE_CV = """\
Jane Doe
jane@example.com

SUMMARY
Backend engineer with 6 years of experience building pipelines.

WORK EXPERIENCE
Senior Software Engineer | Acme Corp
Jan 2020 - Present
• Built async data pipelines with Python
• Led a 4-person team

Software Engineer - Globex
2017 - 2019
- Wrote REST APIs in FastAPI

EDUCATION
BSc Computer Science, MIT (2014 - 2018)

SKILLS
Python, FastAPI, PostgreSQL, Docker, AWS

PROJECTS
PudimJobs - Job application tracker
https://github.com/example/pudimjobs
• Tailors CVs to job descriptions
"""


# --- text extraction -------------------------------------------------------


def test_extract_text_from_pdf_returns_lines():
    pdf = make_pdf("SUMMARY", "Backend engineer.", "SKILLS", "Python")
    text = extract_text_from_pdf(pdf)
    assert "SUMMARY" in text
    assert "Backend engineer." in text
    assert "Python" in text


def test_extract_text_from_docx_includes_paragraphs():
    docx = make_docx("SUMMARY", "Backend engineer.")
    assert extract_text_from_docx(docx) == "SUMMARY\nBackend engineer."


def test_extract_text_dispatches_by_extension():
    assert extract_text("cv.pdf", make_pdf("Hello")) == "Hello"
    assert extract_text("cv.docx", make_docx("Hello")) == "Hello"
    assert extract_text("cv.odt", make_odt("Hello")) == "Hello"


def test_extract_text_from_odt_includes_paragraphs():
    odt = make_odt("SUMMARY", "Backend engineer.", "SKILLS", "Python & FastAPI")
    assert extract_text_from_odt(odt) == ("SUMMARY\nBackend engineer.\nSKILLS\nPython & FastAPI")


def test_extract_text_from_odt_rejects_invalid_bytes():
    with pytest.raises(InvalidFileError):
        extract_text_from_odt(b"not an odt at all")


def test_extract_text_from_odt_rejects_zip_without_content():
    import zipfile
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    with pytest.raises(InvalidFileError):
        extract_text_from_odt(buffer.getvalue())


def test_extract_text_rejects_unknown_extension():
    with pytest.raises(UnsupportedFileTypeError):
        extract_text("cv.txt", b"plain")


def test_extract_text_from_pdf_rejects_invalid_bytes():
    with pytest.raises(InvalidFileError):
        extract_text_from_pdf(b"not a pdf at all")


def test_extract_text_from_docx_rejects_invalid_bytes():
    with pytest.raises(InvalidFileError):
        extract_text_from_docx(b"not a docx at all")


# --- rule-based structuring ------------------------------------------------


def test_structure_cv_parses_all_sections():
    cv = structure_cv(SAMPLE_CV)
    assert "Backend engineer" in cv.summary
    assert len(cv.experience) == 2

    first = cv.experience[0]
    assert first.title == "Senior Software Engineer"
    assert first.company == "Acme Corp"
    assert first.start_date == "2020-01"
    assert first.end_date == "Present"
    assert first.bullets == [
        "Built async data pipelines with Python",
        "Led a 4-person team",
    ]

    second = cv.experience[1]
    assert second.title == "Software Engineer"
    assert second.company == "Globex"
    assert second.start_date == "2017"
    assert second.end_date == "2019"
    assert second.bullets == ["Wrote REST APIs in FastAPI"]

    assert len(cv.education) == 1
    assert cv.education[0].institution == "MIT"
    assert cv.education[0].degree == "BSc Computer Science"
    assert cv.education[0].year == "2014"

    assert cv.skills == ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"]

    assert len(cv.projects) == 1
    assert cv.projects[0].name == "PudimJobs"
    assert cv.projects[0].link == "https://github.com/example/pudimjobs"


def test_structure_cv_empty_text_is_schema_valid():
    cv = structure_cv("")
    assert cv.summary == ""
    assert cv.experience == []
    assert cv.education == []
    assert cv.skills == []
    assert cv.projects == []
    CVStructure.model_validate(cv.model_dump())


def test_structure_cv_ignores_unknown_sections():
    text = (
        "WORK EXPERIENCE\nEngineer | Acme\n2019 - 2021\n- did things\n\n"
        "LANGUAGES\nEnglish\n\n"
        "SKILLS\nPython, SQL\n"
    )
    cv = structure_cv(text)
    assert len(cv.experience) == 1
    assert cv.skills == ["Python", "SQL"]


# --- LLM structuring (graceful degradation) --------------------------------


class _FakeResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeClient:
    """In-memory stand-in for httpx.AsyncClient (mirrors test_cv_tailor)."""

    reply = (
        '{"summary": "LLM summary", "experience": [], "education": [], '
        '"skills": ["llm-skill"], "projects": []}'
    )

    def __init__(self, *args, **kwargs):
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append(json)
        return _FakeResponse(self.reply)


def _llm_config() -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=True,
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )


async def test_structure_cv_with_llm_parses_json(monkeypatch):
    from app.services import cv_parser

    fake = _FakeClient()
    monkeypatch.setattr(cv_parser.httpx, "AsyncClient", lambda *a, **k: fake)

    result = await structure_cv_with_llm("raw text", _llm_config())
    assert result is not None
    assert result.summary == "LLM summary"
    assert result.skills == ["llm-skill"]
    assert fake.requests[0]["messages"][0]["role"] == "system"


async def test_structure_cv_with_llm_returns_none_on_garbage(monkeypatch):
    from app.services import cv_parser

    fake = _FakeClient()
    fake.reply = "not json at all"
    monkeypatch.setattr(cv_parser.httpx, "AsyncClient", lambda *a, **k: fake)

    assert await structure_cv_with_llm("raw text", _llm_config()) is None


async def test_structure_cv_with_llm_returns_none_on_invalid_shape(monkeypatch):
    from app.services import cv_parser

    fake = _FakeClient()
    fake.reply = '{"summary": 123}'
    monkeypatch.setattr(cv_parser.httpx, "AsyncClient", lambda *a, **k: fake)

    assert await structure_cv_with_llm("raw text", _llm_config()) is None


# --- end-to-end parse_cv_file ----------------------------------------------


async def test_parse_cv_file_uses_llm_when_configured(monkeypatch):
    from app.services import cv_parser

    fake = _FakeClient()
    monkeypatch.setattr(cv_parser.httpx, "AsyncClient", lambda *a, **k: fake)

    docx = make_docx("WORK EXPERIENCE", "Engineer | Acme", "Jan 2020 - Present", "- did things")
    result = await parse_cv_file("cv.docx", docx, llm_config=_llm_config())
    assert result.summary == "LLM summary"
    assert result.skills == ["llm-skill"]


async def test_parse_cv_file_falls_back_to_rule_based_when_llm_fails(monkeypatch):
    from app.services import cv_parser

    fake = _FakeClient()
    fake.reply = "boom"
    monkeypatch.setattr(cv_parser.httpx, "AsyncClient", lambda *a, **k: fake)

    docx = make_docx("WORK EXPERIENCE", "Engineer | Acme", "Jan 2020 - Present", "- did things")
    result = await parse_cv_file("cv.docx", docx, llm_config=_llm_config())
    assert result.experience[0].title == "Engineer"
    assert result.experience[0].company == "Acme"
    assert result.experience[0].start_date == "2020-01"
    assert result.experience[0].end_date == "Present"


async def test_parse_cv_file_rule_based_without_llm_config():
    docx = make_docx("WORK EXPERIENCE", "Engineer | Acme", "Jan 2020 - Present", "- did things")
    result = await parse_cv_file("cv.docx", docx)
    assert result.experience[0].title == "Engineer"
    assert result.experience[0].company == "Acme"


async def test_parse_cv_file_pdf_end_to_end():
    pdf = make_pdf("WORK EXPERIENCE", "Engineer | Acme", "2020 - Present", "- did things")
    result = await parse_cv_file("cv.pdf", pdf)
    assert result.experience[0].title == "Engineer"
    assert result.experience[0].company == "Acme"
    assert result.experience[0].start_date == "2020"
    assert result.experience[0].end_date == "Present"


async def test_parse_cv_file_odt_end_to_end():
    odt = make_odt(
        "SUMMARY",
        "Backend engineer.",
        "WORK EXPERIENCE",
        "Engineer | Acme",
        "Jan 2020 - Present",
        "- did things",
        "SKILLS",
        "Python, FastAPI",
    )
    result = await parse_cv_file("cv.odt", odt)
    assert "Backend engineer." in result.summary
    assert result.experience[0].title == "Engineer"
    assert result.experience[0].company == "Acme"
    assert result.experience[0].start_date == "2020-01"
    assert result.experience[0].end_date == "Present"
    assert "Python" in result.skills


# --- richer structure: contact, certifications, languages -------------------


def test_structure_cv_extracts_contact_block():
    cv = structure_cv(SAMPLE_CV)
    assert cv.full_name == "Jane Doe"
    assert cv.email == "jane@example.com"


def test_structure_cv_extracts_phone_location_and_links():
    text = (
        "Jane Doe\n"
        "jane@example.com | +55 11 91234-5678 | Sao Paulo, Brazil\n"
        "https://github.com/janedoe\n"
        "SUMMARY\n"
        "Backend engineer\n"
    )
    cv = structure_cv(text)
    assert cv.full_name == "Jane Doe"
    assert cv.email == "jane@example.com"
    assert cv.phone == "+55 11 91234-5678"
    assert cv.location == "Sao Paulo, Brazil"
    assert cv.links == ["https://github.com/janedoe"]


def test_structure_cv_parses_certifications_and_languages():
    text = (
        "CERTIFICATIONS\n"
        "AWS Certified Solutions Architect, CKA: Certified Kubernetes Administrator\n"
        "LANGUAGES\n"
        "English (fluent), Portuguese (native)\n"
    )
    cv = structure_cv(text)
    assert cv.certifications == [
        "AWS Certified Solutions Architect",
        "CKA: Certified Kubernetes Administrator",
    ]
    assert cv.languages == ["English (fluent)", "Portuguese (native)"]


def test_structure_cv_defaults_contact_when_absent():
    cv = structure_cv("SUMMARY\nBackend engineer\n")
    assert cv.full_name == ""
    assert cv.email == ""
    assert cv.phone == ""
    assert cv.location == ""
    assert cv.links == []
    assert cv.certifications == []
    assert cv.languages == []
