from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

FONT = "Meiryo"
TEXT = RGBColor(0x1F, 0x23, 0x28)
MUTED = RGBColor(0x57, 0x60, 0x6A)
ACCENT = RGBColor(0x09, 0x69, 0xDA)
CATEGORY_COLOR = {"theme": RGBColor(0x82, 0x50, 0xDF), "general": RGBColor(0x1A, 0x7F, 0x37)}

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)
BODY_W = SLIDE_W - MARGIN * 2
# 詳細スライド1枚に載せる文字数の目安（14pt・本文領域でおおよそ収まる量）
DETAIL_CHARS_PER_SLIDE = 650


def _style_run(run, size: int, bold: bool = False, color: RGBColor = TEXT) -> None:
    font = run.font
    font.size = Pt(size)
    font.bold = bold
    font.color.rgb = color
    font.name = FONT
    # 日本語部分のフォント（East Asian）も指定しないと既定フォントになる
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = rpr.makeelement(qn("a:ea"), {})
        rpr.append(ea)
    ea.set("typeface", FONT)


def _textbox(slide, left, top, width, height):
    tf = slide.shapes.add_textbox(left, top, width, height).text_frame
    tf.word_wrap = True
    return tf


def _add_para(tf, text: str, size: int, bold: bool = False, color: RGBColor = TEXT,
              space_after: int = 6, first: bool = False, link: str | None = None):
    para = tf.paragraphs[0] if first else tf.add_paragraph()
    para.space_after = Pt(space_after)
    run = para.add_run()
    run.text = text
    _style_run(run, size, bold, color)
    if link:
        run.hyperlink.address = link
    return para


def _title(slide, text: str, sub: str | None = None) -> None:
    tf = _textbox(slide, MARGIN, Inches(0.35), BODY_W, Inches(1.0))
    _add_para(tf, text, 26, bold=True, first=True, space_after=2)
    if sub:
        _add_para(tf, sub, 12, color=MUTED)


def _split_sentences(text: str, limit: int) -> list[str]:
    """長い本文を「。」区切りで limit 文字以内の塊に分ける。"""
    chunks, current = [], ""
    for sentence in text.replace("。", "。\n").splitlines():
        if current and len(current) + len(sentence) > limit:
            chunks.append(current)
            current = ""
        current += sentence
    if current:
        chunks.append(current)
    return chunks


def _paginate_details(details: list[dict]) -> list[list[tuple[str, str]]]:
    """詳細セクションを、1枚あたりの文字数目安でスライドごとに分ける。"""
    pages: list[list[tuple[str, str]]] = [[]]
    used = 0
    for d in details:
        for i, body in enumerate(_split_sentences(d["body"], DETAIL_CHARS_PER_SLIDE - 40)):
            heading = d["heading"] if i == 0 else f"{d['heading']}（続き）"
            cost = len(body) + 40  # 見出しと余白のぶん
            if pages[-1] and used + cost > DETAIL_CHARS_PER_SLIDE:
                pages.append([])
                used = 0
            pages[-1].append((heading, body))
            used += cost
    return [p for p in pages if p]


def render_pptx(meta: dict, entries: list[dict], path: Path) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    blank = prs.slide_layouts[6]

    # 表紙
    slide = prs.slides.add_slide(blank)
    tf = _textbox(slide, MARGIN, Inches(2.4), BODY_W, Inches(3))
    _add_para(tf, meta["title"], 36, bold=True, first=True)
    _add_para(tf, f"{meta['date']} 作成 ／ 対象: {meta['since']} 以降に作成されたリポジトリ", 16, color=MUTED)
    themes = "、".join(meta["themes"]) or "（なし）"
    _add_para(tf, f"テーマ: {themes}", 16, color=MUTED)

    # 一覧
    slide = prs.slides.add_slide(blank)
    _title(slide, "今週の一覧")
    rows = len(entries) + 1
    table = slide.shapes.add_table(
        rows, 4, MARGIN, Inches(1.3), BODY_W, Inches(0.45) * rows
    ).table
    widths = [Inches(1.0), Inches(3.6), Inches(1.2), BODY_W - Inches(5.8)]
    for col, w in enumerate(widths):
        table.columns[col].width = w
    for col, head in enumerate(["区分", "リポジトリ", "★", "一言で"]):
        run = table.cell(0, col).text_frame.paragraphs[0].add_run()
        run.text = head
        _style_run(run, 12, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
    for row, e in enumerate(entries, 1):
        r, s = e["repo"], e["summary"]
        values = ["テーマ" if r["category"] == "theme" else "総合", r["full_name"], f"{r['stars']:,}", s["one_liner"]]
        for col, value in enumerate(values):
            run = table.cell(row, col).text_frame.paragraphs[0].add_run()
            run.text = value
            _style_run(run, 10)
            if col == 1:
                run.hyperlink.address = r["html_url"]

    # 各リポジトリ
    for i, e in enumerate(entries, 1):
        r, s = e["repo"], e["summary"]
        label = "テーマ" if r["category"] == "theme" else "総合"

        slide = prs.slides.add_slide(blank)
        _title(slide, f"{i}. {r['full_name']}")
        tf = _textbox(slide, MARGIN, Inches(1.15), BODY_W, Inches(6.0))
        _add_para(tf, r["html_url"], 12, color=ACCENT, first=True, link=r["html_url"], space_after=2)
        _add_para(
            tf,
            f"【{label}】 ★ {r['stars']:,} ／ 言語 {r['language'] or '不明'} ／ 作成 {r['created_at'][:10]}",
            12, color=CATEGORY_COLOR[r["category"]], space_after=10,
        )
        _add_para(tf, s["one_liner"], 18, bold=True, space_after=10)
        _add_para(tf, s["summary"], 14, space_after=10)
        for p in s["key_points"]:
            _add_para(tf, f"・{p}", 13, space_after=3)

        for page_no, page in enumerate(_paginate_details(s["details"]), 1):
            slide = prs.slides.add_slide(blank)
            _title(slide, f"{i}. {r['full_name']}", f"詳細 {page_no}")
            tf = _textbox(slide, MARGIN, Inches(1.35), BODY_W, Inches(5.8))
            for j, (heading, body) in enumerate(page):
                _add_para(tf, heading, 15, bold=True, color=ACCENT, first=(j == 0), space_after=2)
                _add_para(tf, body, 13, space_after=10)

        slide = prs.slides.add_slide(blank)
        _title(slide, f"{i}. {r['full_name']}", "技術構成と向いている人")
        tf = _textbox(slide, MARGIN, Inches(1.35), BODY_W, Inches(5.8))
        _add_para(tf, "技術構成", 15, bold=True, color=ACCENT, first=True, space_after=2)
        _add_para(tf, "、".join(s["tech_stack"]) or "不明", 13, space_after=12)
        _add_para(tf, "向いている人・用途", 15, bold=True, color=ACCENT, space_after=2)
        _add_para(tf, s["target_users"], 13)

    prs.save(path)
