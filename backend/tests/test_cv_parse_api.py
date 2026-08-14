"""API tests for POST /api/cv/parse (upload a PDF/DOCX CV)."""

from tests.helpers import make_docx, make_pdf

PDF_BYTES = make_pdf(
    "WORK EXPERIENCE", "Engineer | Acme", "2020 - Present", "- did things"
)
DOCX_BYTES = make_docx(
    "SUMMARY",
    "Backend engineer.",
    "EXPERIENCE",
    "Engineer | Acme",
    "Jan 2020 - Present",
    "- built things",
    "SKILLS",
    "Python, FastAPI",
)

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


async def test_parse_cv_docx_returns_structure(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("resume.docx", DOCX_BYTES, _DOCX_MIME)},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Backend engineer." in body["summary"]
    assert body["experience"][0]["title"] == "Engineer"
    assert body["experience"][0]["company"] == "Acme"
    assert body["experience"][0]["start_date"] == "2020-01"
    assert body["experience"][0]["end_date"] == "Present"
    assert "Python" in body["skills"]


async def test_parse_cv_pdf_returns_structure(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["experience"][0]["title"] == "Engineer"
    assert body["experience"][0]["company"] == "Acme"
    assert body["experience"][0]["start_date"] == "2020"
    assert body["experience"][0]["end_date"] == "Present"


async def test_parse_cv_requires_auth(client):
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("resume.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 401


async def test_parse_cv_rejects_unsupported_extension(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("resume.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


async def test_parse_cv_rejects_invalid_pdf(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400


async def test_parse_cv_rejects_oversized_file(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/parse",
        files={"file": ("big.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert response.status_code == 413
