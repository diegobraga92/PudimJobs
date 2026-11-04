"""Tests for the recruiter-safe CV filename rules (ADR 030)."""

import pytest

from app.services.cv_filename import cv_stem, export_filename, tailored_filename


class TestSlug:
    """A slug is ASCII, hyphen-joined and safe in a ``Content-Disposition``."""

    def test_an_accents_strip_without_losing_the_capitalisation(self):
        assert cv_stem(full_name="José Conceição") == "Jose-Conceicao-CV"

    def test_a_parenthetical_is_dropped_instead_of_being_mangled(self):
        assert tailored_filename(full_name="Ada Lovelace", job_title="Engenheiro (Remoto)") == (
            "Ada-Lovelace-CV-Engenheiro.pdf"
        )

    def test_a_stacked_parenthetical_keeps_the_words_around_it(self):
        assert cv_stem(job_title="Backend [Contract] Engineer") == "CV-Backend-Engineer"

    def test_c_plus_plus_survives_as_a_readable_token(self):
        assert cv_stem(job_title="C++ Developer") == "CV-C-Developer"

    def test_a_name_is_capped_on_a_word_boundary(self):
        stem = cv_stem(full_name="Maximiliano de Albuquerque Nascimento Filho Sobrinho")
        name = stem.removesuffix("-CV")
        assert len(name) <= 48
        assert not name.endswith("-")
        # The cap drops whole words: what is kept is the beginning of the name.
        assert name.startswith("Maximiliano-de-Albuquerque")

    def test_a_role_is_capped_shorter_than_the_name(self):
        role = cv_stem(job_title="Senior Staff Software Engineer, Backend Platform (Remote)")
        assert role == "CV-Senior-Staff-Software-Engineer-Backend"
        assert len(role.removeprefix("CV-")) <= 40

    def test_an_over_long_single_word_is_cut_rather_than_dropped(self):
        assert cv_stem(full_name="A" * 80) == "A" * 48 + "-CV"

    def test_non_ascii_and_punctuation_only_becomes_the_bare_document(self):
        assert cv_stem(full_name="✨✨") == "CV"

    def test_injection_characters_never_reach_the_header(self):
        # A name is user input that lands in a response header: no quote may
        # survive to end the filename, and no newline may split the header.
        assert cv_stem(full_name='Ada"Lovelace\r\n; attachment') == "Ada-Lovelace-attachment-CV"


class TestCvStem:
    """Name, document type, then the role the CV was tailored for."""

    def test_the_approved_shape(self):
        assert (
            tailored_filename(full_name="Ada Lovelace", job_title="Backend Engineer")
            == "Ada-Lovelace-CV-Backend-Engineer.pdf"
        )

    def test_the_name_falls_back_to_the_account_name(self):
        assert cv_stem(account_name="Diego Silva") == "Diego-Silva-CV"

    def test_a_typed_name_wins_over_the_account_name(self):
        assert cv_stem(full_name="Ada Lovelace", account_name="Diego") == "Ada-Lovelace-CV"

    def test_no_name_at_all_degrades_to_the_document(self):
        """Never an empty segment: a nameless account still gets a real file."""
        assert cv_stem() == "CV"
        assert cv_stem(full_name="", account_name="", job_title="Backend Engineer") == (
            "CV-Backend-Engineer"
        )

    @pytest.mark.parametrize("junk", ["CV", "curriculum vitae", "Resume", "Currículo"])
    def test_a_junk_name_never_doubles_the_document_type(self, junk):
        # A parser that read a heading as the candidate's name would otherwise
        # produce "Curriculum-Vitae-CV.pdf".
        assert cv_stem(full_name=junk) == "CV"


class TestExportFilename:
    """The suffixes that keep two exports of one CV from overwriting each other."""

    def test_a_tailored_download_is_named_for_the_role(self):
        assert tailored_filename(
            full_name="Ada Lovelace", job_title="Backend Engineer", language="pt-BR"
        ) == ("Ada-Lovelace-CV-Backend-Engineer-pt-br.pdf")

    def test_docx_never_carries_the_ats_marker(self):
        # The classic/ATS split is a PDF-styling concern (ADR 017).
        assert export_filename("Ada-Lovelace-CV", fmt="docx", template="ats") == (
            "Ada-Lovelace-CV.docx"
        )

    def test_the_ats_template_is_marked(self):
        assert export_filename("Ada-Lovelace-CV", template="ats") == "Ada-Lovelace-CV-ATS.pdf"

    def test_the_default_template_carries_no_marker(self):
        assert export_filename("Ada-Lovelace-CV", template="classic") == "Ada-Lovelace-CV.pdf"

    def test_the_language_follows_the_layout_marker(self):
        assert export_filename("Ada-Lovelace-CV", template="ats", language="pt-BR") == (
            "Ada-Lovelace-CV-ATS-pt-br.pdf"
        )
