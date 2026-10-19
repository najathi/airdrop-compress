"""Document conversion to Markdown (MarkItDown, macOS textutil, or a code block).

Received documents can come from anyone nearby, so MarkItDown's parsers (PDF,
Office, EPUB, ZIP...) run in a separate sandboxed process with a time limit
(see document_worker.py and sandbox.py), and archives are checked for "zip
bombs" before anything unpacks them.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import zipfile
from pathlib import Path

from .. import sandbox
from ..settings import Settings
from .base import Job, Output, Result, SkipFile

log = logging.getLogger("airdrop-compress")

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

# Formats that are ZIP archives inside, checked before they are unpacked.
ARCHIVE_EXTS = {".zip", ".docx", ".pptx", ".xlsx", ".epub", ".odt"}
MAX_UNPACKED_BYTES = 300 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000
MAX_RATIO = 200                 # suspicious if it expands more than 200x...
RATIO_MIN_BYTES = 20 * 1024 * 1024  # ...to more than 20 MB
CONVERT_TIMEOUT = 300           # seconds per document

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


def check_archive(path: Path) -> None:
    """Refuse archives that would expand to an unsafe size (zip bombs)."""
    if path.suffix.lower() not in ARCHIVE_EXTS or not zipfile.is_zipfile(path):
        return
    try:
        with zipfile.ZipFile(path) as z:
            entries = z.infolist()
    except (zipfile.BadZipFile, OSError) as e:
        raise SkipFile(f"damaged archive ({e})")
    unpacked = sum(e.file_size for e in entries)
    packed = max(1, sum(e.compress_size for e in entries))
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise SkipFile(f"contains {len(entries)} files - skipped for safety")
    if unpacked > MAX_UNPACKED_BYTES or (unpacked > RATIO_MIN_BYTES and unpacked / packed > MAX_RATIO):
        raise SkipFile(f"expands to {unpacked // (1024 * 1024)} MB when unpacked - skipped for safety")


def textutil_to_html(src: Path, out_dir: Path) -> Path:
    """Older formats (.doc, .rtf, .odt...) -> HTML with macOS's own converter."""
    html = out_dir / "textutil.html"
    try:
        subprocess.run(["/usr/bin/textutil", "-convert", "html", "-output", str(html), str(src)],
                       check=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError("macOS couldn't read this document within 2 minutes")
    except subprocess.CalledProcessError:
        raise RuntimeError("macOS couldn't read this document - it may be damaged")
    return html


def markitdown_isolated(src: Path, workdir: Path) -> str:
    """Run MarkItDown in a sandboxed child process (in-process if the sandbox is missing)."""
    if not sandbox.available():
        log.warning("sandbox-exec is unavailable; converting %s without isolation", src.name)
        return markitdown().convert(str(src)).markdown
    box = workdir / "sandbox"
    box.mkdir(exist_ok=True)
    out = box / "result.md"
    profile = box / "profile.sb"
    profile.write_text(sandbox.profile(read_files=[src], write_dir=box))
    cmd, env_extra = sandbox.python_command("airdrop_compress.processors.document_worker", "--convert-document")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(box), "TMPDIR": str(box), "LANG": "en_US.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", **env_extra}
    try:
        proc = subprocess.run(sandbox.command(profile, cmd), input=json.dumps({"input": str(src), "output": str(out)}),
                              capture_output=True, text=True, timeout=CONVERT_TIMEOUT, env=env, cwd=str(box))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"took longer than {CONVERT_TIMEOUT // 60} minutes to convert and was stopped")
    from .document_worker import RESULT_MARK
    result = next((json.loads(line[len(RESULT_MARK):]) for line in proc.stdout.splitlines()
                   if line.startswith(RESULT_MARK)), None)
    if result is None:
        tail = " ".join(proc.stderr.strip().splitlines()[-2:])[:300]
        log.error("Document converter crashed on %s (exit %s): %s", src.name, proc.returncode, tail)
        raise RuntimeError("the document converter crashed - the file may be damaged")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "conversion failed")
    return out.read_text(encoding="utf-8")


def document_to_markdown(src: Path) -> str:
    """In-process conversion (used by the sandboxed worker, and as a fallback)."""
    ext = src.suffix.lower()
    if ext in CODE_EXTS:
        body = src.read_bytes().decode("utf-8", errors="replace")
        fence = "```"
        while fence in body:
            fence += "`"
        return f"# {src.name}\n\n{fence}{CODE_EXTS[ext]}\n{body.rstrip()}\n{fence}\n"
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
        check_archive(job.src)
        ext = job.src.suffix.lower()
        if ext in CODE_EXTS:  # plain text: no parser involved
            raw, source = document_to_markdown(job.src), job.src
        else:
            source = textutil_to_html(job.src, job.workdir) if ext in TEXTUTIL_EXTS else job.src
            raw = markitdown_isolated(source, job.workdir)
        # Converters sometimes quote the full path (e.g. "Content from the zip file /Users/...").
        text = tidy_markdown(raw.replace(str(source), job.src.name).replace(str(job.src), job.src.name))
        if not text.strip():
            raise SkipFile("no text found - a scanned or image-only document?")
        out = job.workdir / "main.md"
        out.write_text(text, encoding="utf-8")
        return Result([Output(out, ".md", "Markdown")])
