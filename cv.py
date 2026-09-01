from pathlib import Path

from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
COURSE_TWIN = HERE.parents[1] / "1_foundations" / "twin"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_cv() -> str:
    summary = _read(HERE / "summary.txt") or _read(COURSE_TWIN / "summary.txt")
    pdf = HERE / "resume.pdf"
    if not pdf.exists():
        pdf = COURSE_TWIN / "linkedin.pdf"
    linkedin = ""
    if pdf.exists():
        reader = PdfReader(pdf)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                linkedin += text + "\n"
    if not summary and not linkedin:
        return "No CV found. Add summary.txt and optionally resume.pdf next to app.py."
    return f"# Summary\n{summary}\n\n# Resume\n{linkedin}".strip()
