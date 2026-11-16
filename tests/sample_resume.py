"""Builds a sample resume (DOCX / PDF) for tests and the cURL walkthrough."""
from pathlib import Path

SAMPLE_LINES = [
    "ARUN KUMAR S",
    "arun.kumar@example.com | +91 98765 43210 | Salem, Tamil Nadu",
    "linkedin.com/in/arunkumar",
    "SUMMARY",
    "Backend developer with 1.5 years of experience building REST APIs.",
    "EDUCATION",
    "B.E. Computer Science and Engineering, Example College of Technology, 2021 - 2025",
    "SKILLS",
    "Languages: Python, JavaScript, SQL",
    "Frameworks: FastAPI, React",
    "Tools: Git, Docker, PostgreSQL",
    "EXPERIENCE",
    "Backend Intern at Acme Technologies   Jun 2024 - Dec 2024",
    "• Built REST APIs using FastAPI",
    "• Wrote optimized SQL queries",
    "Software Developer - Example Corp   Jan 2025 - Mar 2025",
    "• Worked on authentication and 2FA flows",
    "PROJECTS",
    "Attendance Tracker - FastAPI and PostgreSQL",
]


def build_docx(path: Path) -> Path:
    from docx import Document

    doc = Document()
    for line in SAMPLE_LINES:
        doc.add_paragraph(line)
    doc.save(str(path))
    return path


def build_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in SAMPLE_LINES:
        pdf.drawString(50, y, line.replace("•", "-"))
        y -= 18
    pdf.save()
    return path


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_resume.docx")
    build_docx(target)
    print(f"wrote {target}")
