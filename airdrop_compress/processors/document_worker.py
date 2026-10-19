"""Converts one document to Markdown inside the sandbox (see documents.markitdown_isolated).

Started as ``<app> --convert-document`` (packaged app) or
``python -m airdrop_compress.processors.document_worker``. Reads {"input", "output"}
as JSON on stdin and prints one result line prefixed with RESULT_MARK.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULT_MARK = "@@AIRDROP-COMPRESS-DOCUMENT@@"


def main() -> int:
    request = json.loads(sys.stdin.read())
    real_stdout, sys.stdout = sys.stdout, sys.stderr  # library chatter goes to stderr
    try:
        from .documents import markitdown
        text = markitdown().convert(request["input"]).markdown
        Path(request["output"]).write_text(text, encoding="utf-8")
        result = {"ok": True}
    except Exception as e:  # report, don't crash: the parent turns this into a clear message
        result = {"ok": False, "error": friendly_error(e)}
    finally:
        sys.stdout = real_stdout
    print(RESULT_MARK + json.dumps(result), flush=True)
    return 0


def friendly_error(e: Exception) -> str:
    name = type(e).__name__
    if name in ("UnsupportedFormatException", "FileConversionException"):
        return "this file couldn't be read as a document - it may be damaged or a different format"
    if isinstance(e, MemoryError):
        return "the document is too large to convert"
    return f"{name}: {str(e).splitlines()[0][:200] if str(e) else 'conversion failed'}"


if __name__ == "__main__":
    sys.exit(main())
