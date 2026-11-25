"""多格式解析测试：docx / pdf 由测试现场生成，不依赖外部样本。"""

from __future__ import annotations

from pathlib import Path

import docx
import fitz
import pytest

from ingest.parsers import parse_file


def _make_docx(path: Path) -> None:
    d = docx.Document()
    d.add_heading("设备维护手册", level=1)
    d.add_heading("更换滤芯", level=2)
    d.add_paragraph("每 500 小时更换一次滤芯，型号 FX-200。")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "型号"
    t.cell(0, 1).text = "周期"
    t.cell(1, 0).text = "FX-200"
    t.cell(1, 1).text = "500 小时"
    d.save(str(path))


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Annual Report 2026", fontsize=22)
    page.insert_text((72, 130), "Revenue grew to 12.5 million USD in Q3.", fontsize=11)
    page.insert_text((72, 160), "Operating margin reached 18 percent.", fontsize=11)
    doc.save(str(path))
    doc.close()


def test_parse_docx_keeps_headings_and_table(tmp_path: Path):
    p = tmp_path / "manual.docx"
    _make_docx(p)
    doc = parse_file(p, prefer_docling=False)
    assert doc.meta["backend"] == "python-docx"
    assert "# 设备维护手册" in doc.text
    assert "## 更换滤芯" in doc.text
    assert "FX-200" in doc.text
    assert "| 型号 | 周期 |" in doc.text


def test_parse_pdf_extracts_text(tmp_path: Path):
    p = tmp_path / "report.pdf"
    _make_pdf(p)
    doc = parse_file(p, prefer_docling=False)
    assert doc.meta["backend"] == "pymupdf"
    assert "Annual Report 2026" in doc.text
    assert "12.5 million" in doc.text


def test_parse_pdf_detects_big_title_as_heading(tmp_path: Path):
    import re

    p = tmp_path / "report2.pdf"
    _make_pdf(p)
    doc = parse_file(p, prefer_docling=False)
    assert re.search(r"^#{1,6} Annual Report 2026$", doc.text, re.MULTILINE)


def test_unknown_suffix_rejected(tmp_path: Path):
    p = tmp_path / "a.xyz"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_file(p)


def test_loader_accepts_pdf_pdf_and_docx(tmp_path: Path):
    _make_pdf(tmp_path / "a.pdf")
    _make_docx(tmp_path / "b.docx")
    (tmp_path / "c.md").write_text("# C\n正文", encoding="utf-8")
    from ingest.loader import load_directory

    docs = load_directory(tmp_path)
    assert len(docs) == 3
    assert {d.meta["suffix"] for d in docs} == {".pdf", ".docx", ".md"}
