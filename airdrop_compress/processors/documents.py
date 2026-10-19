"""Document conversion to Markdown (MarkItDown, macOS textutil, or a code block)."""

from __future__ import annotations

import re
import subprocess
import tempfile
import threading
from pathlib import Path

from ..settings import Settings
from .base import Job, Output, Result, SkipFile

# Converted by MarkItDown (https://github.com/microsoft/markitdown).
MARKITDOWN_EXTS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".html", ".htm", ".xhtml",
    ".json", ".txt", ".text", ".md", ".markdown", ".epub", ".ipynb", ".msg", ".zip",
}
# Older formats: macOS's built-in `textutil` turns them into HTML first.
TEXTUTIL_EXTS = {".doc", ".rtf", ".odt", ".webarchive", ".wordml"}
# Plain-text files kept as a fenced code block (extension -> highlighting language).
CODE_EXTS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".jsx": "jsx", ".tsx": "tsx",
    ".sh": "bash", ".zsh": "bash", ".sql": "sql", ".php": "php", ".rb": "ruby",
    ".go": "go", ".java": "java", ".kt": "kotlin", ".swift": "swift", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".cs": "csharp", ".rs": "rust", ".css": "css",
    ".scss": "scss", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".ini": "ini", ".env": "", ".log": "", ".tex": "latex", ".vcf": "", ".ics": "",
    ".jsonl": "json",
}
DOCUMENT_EXTS = MARKITDOWN_EXTS | TEXTUTIL_EXTS | set(CODE_EXTS)

_local = threading.local()


def markitdown():
    # One converter per worker thread; the import is slow, so only pay for it when needed.
    if not hasattr(_local, "md"):
        from markitdown import MarkItDown
        _local.md = MarkItDown(enable_plugins=False)
    return _local.md


def tidy_markdown(text: str) -> str:
    """Strip trailing spaces, page-break characters and runs of blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def document_to_markdown(src: Path) -> str:
    ext = src.suffix.lower()
    if ext in CODE_EXTS:
        body = src.read_bytes().decode("utf-8", errors="replace")
        fence = "```"
        while fence in body:
            fence += "`"
        return f"# {src.name}\n\n{fence}{CODE_EXTS[ext]}\n{body.rstrip()}\n{fence}\n"
    if ext in TEXTUTIL_EXTS:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / f"{src.stem}.html"
            subprocess.run(
                ["/usr/bin/textutil", "-convert", "html", "-output", str(html), str(src)],
                check=True, capture_output=True, timeout=300,
            )
            return markitdown().convert(str(html)).markdown
    return markitdown().convert(str(src)).markdown


class DocumentProcessor:
    id = "builtin.documents"
    name = "Document converter"
    kind = "document"

    def handles(self, path: Path, settings: Settings) -> bool:
        return settings.documents.enabled and path.suffix.lower() in DOCUMENT_EXTS

    def process(self, job: Job) -> Result:
        limit = job.settings.documents.max_size_mb
        if job.src.stat().st_size > limit * 1024 * 1024:
            raise SkipFile(f"larger than {limit} MB")
        # Converters sometimes quote the full path (e.g. "Content from the zip file /Users/...").
        text = tidy_markdown(document_to_markdown(job.src).replace(str(job.src), job.src.name))
        if not text.strip():
            raise SkipFile("no text found - a scanned or image-only document?")
        out = job.workdir / "main.md"
        out.write_text(text, encoding="utf-8")
        return Result([Output(out, ".md", "Markdown")])
