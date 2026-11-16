"""Heuristic resume parser: PDF/DOCX -> text -> structured fields.

Rule-based (regex + section detection), so results are best-effort. The user always
reviews and edits the autofilled form before submitting.
"""
import io
import logging
import re
import zipfile
from datetime import date
from typing import Optional

from app.schemas.common import EMAIL_RE, normalize_phone
from app.schemas.resume import ExperienceItem, ParsedResume

logging.getLogger("pdfminer").setLevel(logging.ERROR)  # silence harmless font warnings

MAX_PDF_PAGES = 10
MAX_DOCX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_SKILLS = 50
MAX_EXPERIENCE_ENTRIES = 20


class ResumeParseError(Exception):
    """The uploaded file could not be read as a resume."""


# --------------------------------------------------------------------------- text extraction


def extract_text(data: bytes, ext: str) -> str:
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    raise ResumeParseError("Unsupported file type")


def _extract_pdf(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise ResumeParseError("File content is not a valid PDF")
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [_page_text(page) for page in pdf.pages[:MAX_PDF_PAGES]]
    except Exception as exc:
        raise ResumeParseError("Could not read the PDF (corrupt or password-protected)") from exc
    return "\n".join(pages)


# ---- column-aware PDF text -------------------------------------------------------------------
# Plain extract_text() merges side-by-side columns into single lines ("WORK EXPERIENCE CORE
# COMPETENCIES"), which hides every section heading. We detect a vertical gutter from word
# positions and read each column top-to-bottom instead.


def _page_text(page) -> str:
    plain = page.extract_text() or ""
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        split_x = _find_gutter(words, float(page.width))
        return plain if split_x is None else _two_column_text(words, split_x)
    except Exception:
        return plain


def _median_height(words: list) -> float:
    heights = sorted(w["bottom"] - w["top"] for w in words)
    return heights[len(heights) // 2] if heights else 10.0


def _cluster_lines(words: list, med: float) -> list:
    tol = max(2.5, med * 0.5)
    lines: list = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]) <= tol:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in lines]


def _join_line(ws: list, med: float) -> str:
    parts = [ws[0]["text"]]
    for prev, cur in zip(ws, ws[1:]):
        parts.append("  " if cur["x0"] - prev["x1"] > med * 1.2 else " ")
        parts.append(cur["text"])
    return "".join(parts)


def _find_gutter(words: list, width: float) -> Optional[float]:
    if len(words) < 40 or width <= 0:
        return None
    med = _median_height(words)
    n_lines = max(1, len(_cluster_lines(words, med)))
    band = 3
    counts = {
        x: sum(1 for w in words if w["x0"] < x + band and w["x1"] > x - band)
        for x in range(int(width * 0.2), int(width * 0.8) + 1)
    }
    best = min(counts.values())
    if best > 0.35 * n_lines:  # words cross every x position: a single-column page
        return None
    xs = sorted(x for x, c in counts.items() if c == best)
    runs, run = [], [xs[0]]
    for x in xs[1:]:
        if x == run[-1] + 1:
            run.append(x)
        else:
            runs.append(run)
            run = [x]
    runs.append(run)
    longest = max(runs, key=len)
    split_x = (longest[0] + longest[-1]) / 2

    left = [w for w in words if w["x1"] <= split_x]
    right = [w for w in words if w["x0"] >= split_x]
    if len(left) < 0.12 * len(words) or len(right) < 0.12 * len(words):
        return None
    right_lines = _cluster_lines(right, med)
    if len(right_lines) < 8:
        return None
    texts = [_join_line(ws, med) for ws in right_lines]
    if sum(len(t.split()) for t in texts) / len(texts) < 2.0:
        return None
    if sum(1 for t in texts if DATE_RANGE_RE.search(t)) > 0.5 * len(texts):
        return None  # right-aligned dates in a single-column resume, not a real column
    starts = sorted(ws[0]["x0"] for ws in right_lines)
    median_start = starts[len(starts) // 2]
    if sum(1 for s in starts if abs(s - median_start) <= 8) < 0.6 * len(starts):
        return None
    return split_x


def _two_column_text(words: list, split_x: float) -> str:
    med = _median_height(words)
    band = 3
    spanning = sorted(
        (w for w in words if w["x0"] < split_x + band and w["x1"] > split_x - band),
        key=lambda w: w["top"],
    )
    zones: list = []  # vertical ranges holding full-width text (summary paragraphs etc.)
    for w in spanning:
        if zones and w["top"] - zones[-1][1] <= med * 1.8:
            zones[-1][1] = max(zones[-1][1], w["bottom"])
        else:
            zones.append([w["top"], w["bottom"]])

    buckets: dict = {}
    for w in words:
        cy = (w["top"] + w["bottom"]) / 2
        placed = False
        for i, (y0, y1) in enumerate(zones):
            if y0 - 1 <= cy <= y1 + 1:
                buckets.setdefault(2 * i + 1, {"full": [], "left": [], "right": []})["full"].append(w)
                placed = True
                break
        if not placed:
            k = sum(1 for z in zones if z[1] < cy)
            side = "left" if (w["x0"] + w["x1"]) / 2 < split_x else "right"
            buckets.setdefault(2 * k, {"full": [], "left": [], "right": []})[side].append(w)

    out: list = []
    for idx in sorted(buckets):
        b = buckets[idx]
        for side in (("full",) if idx % 2 else ("left", "right")):
            out.extend(_join_line(ws, med) for ws in _cluster_lines(b[side], med))
    return "\n".join(out)


def _extract_docx(data: bytes) -> str:
    if not data.startswith(b"PK\x03\x04"):
        raise ResumeParseError("File content is not a valid DOCX")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if sum(i.file_size for i in zf.infolist()) > MAX_DOCX_UNCOMPRESSED:
                raise ResumeParseError("DOCX file is too large when uncompressed")
    except zipfile.BadZipFile as exc:
        raise ResumeParseError("File content is not a valid DOCX") from exc

    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(io.BytesIO(data))
        lines = []
        # Walk the body in document order so table-based layouts keep their reading order.
        for child in doc.element.body.iterchildren():
            if child.tag.endswith("}p"):
                lines.append(Paragraph(child, doc).text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, doc).rows:
                    seen = set()
                    for cell in row.cells:
                        if id(cell._tc) in seen:
                            continue
                        seen.add(id(cell._tc))
                        lines.extend(p.text for p in cell.paragraphs)
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError("Could not read the DOCX file") from exc
    return "\n".join(lines)


# --------------------------------------------------------------------------- public entry points


def parse_resume_bytes(data: bytes, ext: str) -> ParsedResume:
    text = extract_text(data, ext)
    if len(text.strip()) < 30:
        raise ResumeParseError("No readable text found (scanned image-only PDFs are not supported)")
    return parse_resume_text(text)


def parse_resume_text(text: str) -> ParsedResume:
    text = text.replace(" ", " ").replace("\t", "  ")
    lines = [re.sub(r"[ ]+$", "", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    sections = _split_sections(lines)

    experience = extract_experience(sections.get("experience", []))
    return ParsedResume(
        name=extract_name(lines),
        email=extract_email(text),
        phone=extract_phone(lines),
        qualification=extract_qualification(sections.get("education", [])),
        skills=extract_skills(sections.get("skills", []), text),
        experience=experience,
        total_experience_years=estimate_total_years(sections.get("experience", []), text),
    )


# --------------------------------------------------------------------------- sections

_SECTION_ALIASES = {
    "skills": [
        "skills", "technical skills", "key skills", "core competencies", "technologies",
        "tech stack", "skill set", "technical proficiency", "core skills", "areas of expertise",
        "technical expertise", "expertise", "competencies",
    ],
    "experience": [
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "internships", "internship experience",
        "internship",
    ],
    "education": [
        "education", "academic background", "academics", "qualification", "qualifications",
        "educational qualification", "educational qualifications", "education details",
    ],
    "other": [
        "projects", "academic projects", "certifications", "achievements", "summary",
        "objective", "profile", "career objective", "professional summary", "summary of qualifications", "languages",
        "interests", "hobbies", "references", "declaration", "awards", "publications",
        "personal details", "personal information", "contact",
    ],
}
_HEADING_LOOKUP = {alias: key for key, aliases in _SECTION_ALIASES.items() for alias in aliases}


def _heading_key(text: str) -> Optional[str]:
    cleaned = re.sub(r"[^a-z ]", "", text.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if 0 < len(cleaned) <= 40:
        return _HEADING_LOOKUP.get(cleaned)
    return None


def _split_sections(lines: list) -> dict:
    sections: dict = {}
    current = None
    for line in lines:
        key = _heading_key(line.rstrip(":"))
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        if ":" in line:  # "Skills: Python, SQL" -> heading with inline content
            head, rest = line.split(":", 1)
            key = _heading_key(head)
            if key and rest.strip():
                current = key
                sections.setdefault(current, []).append(rest.strip())
                continue
        if current:
            sections[current].append(line)
    return sections


# --------------------------------------------------------------------------- simple fields


def extract_email(text: str) -> Optional[str]:
    match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}", text)
    if match and EMAIL_RE.match(match.group(0)):
        return match.group(0).lower()
    return None


_PHONE_CANDIDATE = re.compile(r"\+?\d[\d\s().\-]{8,16}\d")


def extract_phone(lines: list) -> Optional[str]:
    # Contact details sit at the top, so search there first.
    for chunk in (lines[:15], lines):
        for line in chunk:
            for match in _PHONE_CANDIDATE.finditer(line):
                try:
                    return normalize_phone(match.group(0))
                except ValueError:
                    continue
    return None


_NOT_A_NAME = re.compile(
    r"resume|curriculum|vitae|\bcv\b|profile|summary|objective|contact|address|@|http|www\.|linkedin|github",
    re.I,
)
_NAME_WORD = re.compile(r"^(?:[A-Z][A-Za-z.'\-]*|[A-Z.]+)$")


def extract_name(lines: list) -> Optional[str]:
    for line in lines[:6]:
        if _NOT_A_NAME.search(line) or sum(c.isdigit() for c in line) > 0 or len(line) > 50:
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(_NAME_WORD.match(w) for w in words):
            return " ".join(w.capitalize() if w.isupper() and len(w) > 1 else w for w in words)
    return None


# --------------------------------------------------------------------------- education

_DEGREE_LONG = re.compile(
    r"(?<![A-Za-z])(?:B\.?\s?Tech|M\.?\s?Tech|B\.?\s?Sc|M\.?\s?Sc|BCA|MCA|MBA|BBA|Ph\.?\s?D|"
    r"Bachelor|Master|Diploma|Higher Secondary|HSC|SSLC)(?![A-Za-z])",
    re.I,
)
_DEGREE_SHORT = re.compile(r"(?<![A-Za-z])(?:B\.?E|M\.?E|B\.?A|M\.?A|B\.?Com|M\.?Com)\.?(?![A-Za-z])")


def extract_qualification(education_lines: list) -> Optional[str]:
    for i, line in enumerate(education_lines):
        if _DEGREE_LONG.search(line) or _DEGREE_SHORT.search(line):
            # A degree name often wraps in a narrow column ("...Electronics" / "Engineering").
            if i + 1 < len(education_lines):
                nxt = education_lines[i + 1]
                if len(nxt.split()) <= 2 and not re.search(r"\d|\|", nxt) and not _heading_key(nxt):
                    line = f"{line} {nxt}"
            return line[:200]
    return None


# --------------------------------------------------------------------------- skills

_KNOWN_SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Kotlin", "Swift", "PHP", "Ruby",
    "Rust", "Scala", "Dart", "SQL", "NoSQL", "HTML", "CSS", "FastAPI", "Django", "Flask",
    "Spring Boot", "Node.js", "Express.js", "React", "React Native", "Angular", "Vue.js",
    "Next.js", ".NET", "Flutter", "PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis",
    "SQLAlchemy", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Linux", "Git", "GitHub",
    "CI/CD", "REST API", "GraphQL", "Pandas", "NumPy", "Scikit-learn", "TensorFlow", "PyTorch",
    "Machine Learning", "Deep Learning", "NLP", "Data Analysis", "Power BI", "Tableau",
    "Excel", "Tailwind CSS", "Bootstrap", "Postman", "Jira", "Figma", "Celery", "RabbitMQ",
    "Kafka", "Pydantic", "JWT", "OAuth", "Selenium", "Pytest",
]
_SKILL_LOOKUP = {s.lower(): s for s in _KNOWN_SKILLS}
_SKILL_RE = re.compile(
    r"(?<![A-Za-z0-9+#.])(?:"
    + "|".join(re.escape(s) for s in sorted(_KNOWN_SKILLS, key=len, reverse=True))
    + r")(?![A-Za-z0-9+#])",
    re.I,
)
_BULLET = re.compile(r"^[•●▪◦‣\-\*–—·]+\s*")


def extract_skills(skill_lines: list, full_text: str) -> list:
    found: list = []
    seen = set()

    def add(name: str) -> None:
        name = name.strip(" .;:")
        key = name.lower()
        if name and key not in seen and len(name) <= 40 and "@" not in name:
            seen.add(key)
            found.append(_SKILL_LOOKUP.get(key, name))

    for line in skill_lines:
        line = _BULLET.sub("", line)
        if ":" in line:
            line = line.split(":", 1)[1]
        line = re.sub(r"\s*\(.*?\)", "", line)
        for part in re.split(r"[,;|•·●▪]|\s{2,}", line):
            part = part.strip()
            if part and len(part.split()) <= 4:
                add(part)

    for match in _SKILL_RE.finditer(full_text):
        add(match.group(0))
    return found[:MAX_SKILLS]


# --------------------------------------------------------------------------- experience

_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_POINT = rf"(?:{_MON}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_END = rf"(?:{_POINT}|Present|Current|Till\s+date|Now|Ongoing)"
DATE_RANGE_RE = re.compile(
    rf"(?<!\d)({_POINT})\s*(?:-|–|—|·|→|to)\s*({_END})(?!\d)", re.I
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _split_title_company(header: str):
    header = _BULLET.sub("", header).strip(" \t-–—|,:")
    parts = re.split(r"\s+(?:at|@)\s+|\s+[-–—|]\s+|,\s+", header, maxsplit=1)
    title = parts[0].strip() or None
    company = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return title, company


def extract_experience(lines: list) -> list:
    if not lines:
        return []
    date_idx = [i for i, ln in enumerate(lines) if DATE_RANGE_RE.search(ln)]
    items = []

    if not date_idx:
        current = None
        for ln in lines:
            if not _is_bullet(ln) and len(ln) <= 100:
                title, company = _split_title_company(ln)
                current = {"title": title, "company": company, "desc": []}
                items.append(current)
            elif current is not None:
                current["desc"].append(_BULLET.sub("", ln))
        return [
            ExperienceItem(
                title=i["title"], company=i["company"],
                description=" ".join(i["desc"])[:500] or None,
            )
            for i in items[:MAX_EXPERIENCE_ENTRIES]
        ]

    headers = []
    for k, i in enumerate(date_idx):
        match = DATE_RANGE_RE.search(lines[i])
        remainder = (lines[i][: match.start()] + " " + lines[i][match.end():]).strip(" \t-–—|,:()")
        from_prev = False
        if not re.search(r"[A-Za-z]", remainder):
            prev = i - 1
            if (
                prev >= 0 and prev not in date_idx and not _is_bullet(lines[prev])
                and len(lines[prev]) <= 100 and (k == 0 or prev > date_idx[k - 1])
            ):
                remainder, from_prev = lines[prev], True
        headers.append((remainder, from_prev, match.group(0)))

    for k, i in enumerate(date_idx):
        end = date_idx[k + 1] if k + 1 < len(date_idx) else len(lines)
        if k + 1 < len(date_idx) and headers[k + 1][1]:
            end -= 1
        title, company = _split_title_company(headers[k][0])
        start = i + 1
        # Layout "Title / dates / Company | Location": the line after the dates names the company.
        if headers[k][1] and company is None and start < end:
            nxt = lines[start]
            if (
                not _is_bullet(nxt) and len(nxt) <= 80 and not nxt.isupper()
                and ("|" in nxt or len(nxt.split()) <= 6)
            ):
                company = re.split(r"\s+[|–—-]\s+", nxt)[0].strip() or None
                start += 1
        desc = " ".join(_BULLET.sub("", ln) for ln in lines[start:end])[:500] or None
        items.append(ExperienceItem(title=title, company=company, duration=headers[k][2][:60], description=desc))
    return items[:MAX_EXPERIENCE_ENTRIES]


def _to_ym(token: str, is_end: bool, today: date):
    t = token.strip().lower()
    if re.fullmatch(r"present|current|till\s+date|now|ongoing", t):
        return today.year, today.month
    m = re.fullmatch(r"([a-z]+)\.?\s+(\d{4})", t)
    if m and m.group(1)[:3] in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1)[:3]]
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        return int(m.group(1)), (12 if is_end else 1)
    return None


def estimate_total_years(experience_lines: list, full_text: str, today: Optional[date] = None) -> Optional[float]:
    today = today or date.today()
    today_idx = today.year * 12 + today.month
    spans = []
    for line in experience_lines:
        match = DATE_RANGE_RE.search(line)
        if not match:
            continue
        start = _to_ym(match.group(1), False, today)
        end = _to_ym(match.group(2), True, today)
        if not start or not end:
            continue
        s, e = start[0] * 12 + start[1], min(end[0] * 12 + end[1], today_idx)
        if e >= s:
            spans.append((s, e))
    if spans:
        spans.sort()
        merged = [list(spans[0])]
        for s, e in spans[1:]:
            if s <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        months = sum(e - s + 1 for s, e in merged)
        return round(months / 12, 1)

    m = re.search(
        r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|work\s+)?experience",
        full_text, re.I,
    )
    return float(m.group(1)) if m else None
