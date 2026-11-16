import pytest

from app.services.resume_parser import ResumeParseError, parse_resume_bytes, parse_resume_text
from tests.sample_resume import SAMPLE_LINES, build_docx, build_pdf


def _check(parsed):
    assert parsed.name == "Arun Kumar S"
    assert parsed.email == "arun.kumar@example.com"
    assert parsed.phone == "+919876543210"
    assert parsed.qualification.startswith("B.E. Computer Science")
    for skill in ["Python", "JavaScript", "SQL", "FastAPI", "React", "Git", "Docker", "PostgreSQL"]:
        assert skill in parsed.skills
    assert len(parsed.skills) == len({s.lower() for s in parsed.skills})
    assert len(parsed.experience) == 2
    first, second = parsed.experience
    assert (first.title, first.company) == ("Backend Intern", "Acme Technologies")
    assert first.duration == "Jun 2024 - Dec 2024"
    assert "FastAPI" in first.description
    assert (second.title, second.company) == ("Software Developer", "Example Corp")
    assert parsed.total_experience_years == 0.8  # 7 + 3 months = 10 months


def test_parse_docx(tmp_path):
    path = build_docx(tmp_path / "r.docx")
    _check(parse_resume_bytes(path.read_bytes(), ".docx"))


def test_parse_pdf(tmp_path):
    pytest.importorskip("reportlab")
    path = build_pdf(tmp_path / "r.pdf")
    _check(parse_resume_bytes(path.read_bytes(), ".pdf"))


def test_plain_text_parse():
    _check(parse_resume_text("\n".join(SAMPLE_LINES)))


def test_rejects_wrong_magic_bytes():
    with pytest.raises(ResumeParseError):
        parse_resume_bytes(b"this is not a pdf at all", ".pdf")
    with pytest.raises(ResumeParseError):
        parse_resume_bytes(b"this is not a docx at all", ".docx")


def test_rejects_corrupt_pdf():
    with pytest.raises(ResumeParseError):
        parse_resume_bytes(b"%PDF-1.4 garbage garbage garbage", ".pdf")


def test_experience_with_dates_on_their_own_line():
    text = "\n".join([
        "Jane Doe", "jane@example.com", "EXPERIENCE",
        "Data Analyst, Acme Technologies", "2022 - 2024", "- Built dashboards",
        "QA Engineer at Globex", "Jan 2024 - Present", "- Wrote tests",
        "EDUCATION", "B.Sc. Mathematics, Example University",
    ])
    parsed = parse_resume_text(text)
    assert [(e.title, e.company) for e in parsed.experience] == [
        ("Data Analyst", "Acme Technologies"),
        ("QA Engineer", "Globex"),
    ]
    assert parsed.experience[0].duration == "2022 - 2024"
    assert parsed.experience[0].description == "Built dashboards"
    assert parsed.experience[1].description == "Wrote tests"
    assert parsed.qualification.startswith("B.Sc.")


def test_missing_fields_return_none_not_errors():
    parsed = parse_resume_text("just some text without any structure but long enough to pass the guard")
    assert parsed.name is None and parsed.email is None and parsed.phone is None
    assert parsed.experience == [] and parsed.qualification is None
