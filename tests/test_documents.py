import subprocess

import pytest

from airdrop_compress.processors.base import Job, SkipFile
from airdrop_compress.processors.documents import DocumentProcessor, tidy_markdown
from airdrop_compress.settings import from_dict


def convert(src, tmp_path, **doc_settings):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    result = DocumentProcessor().process(Job(src, work, from_dict({"documents": doc_settings})))
    return result.outputs[0].path.read_text()


def test_html_table(tmp_path):
    src = tmp_path / "report.html"
    src.write_text("<h1>Report</h1><table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>£2</td></tr></table>")
    md = convert(src, tmp_path)
    assert "# Report" in md and "| A | B |" in md and "£2" in md


def test_rtf_via_textutil(tmp_path):
    html = tmp_path / "x.html"
    html.write_text("<meta charset='utf-8'><p>Hello <b>world</b></p>")
    rtf = tmp_path / "x.rtf"
    subprocess.run(["/usr/bin/textutil", "-convert", "rtf", str(html), "-output", str(rtf)], check=True)
    assert "Hello **world**" in convert(rtf, tmp_path)


def test_code_is_fenced(tmp_path):
    src = tmp_path / "script.py"
    src.write_text("print('```')\n")
    md = convert(src, tmp_path)
    assert md.startswith("# script.py") and "````python" in md


def test_empty_document_is_skipped(tmp_path):
    src = tmp_path / "empty.txt"
    src.write_text("   \n\n")
    with pytest.raises(SkipFile):
        convert(src, tmp_path)


def test_size_limit(tmp_path):
    src = tmp_path / "big.txt"
    src.write_bytes(b"a" * (2 * 1024 * 1024))
    with pytest.raises(SkipFile, match="larger than 1 MB"):
        convert(src, tmp_path, max_size_mb=1)


def test_tidy():
    assert tidy_markdown("a  \r\n\n\n\n\fb") == "a\n\nb\n"
