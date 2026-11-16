"""Create scripts/sample_resume.docx for the cURL walkthrough: python scripts/make_sample_resume.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.sample_resume import build_docx  # noqa: E402

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "sample_resume.docx"
build_docx(target)
print(f"wrote {target}")
