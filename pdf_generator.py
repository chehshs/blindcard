"""赤シート対応の暗記カード PDF を生成する。"""

from __future__ import annotations

import io
import os
import re
from typing import Iterable, Mapping, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, A6
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

PAGE_SIZES = {
    "A6": A6,
    "A5": A5,
    "A4": A4,
}
ALLOWED_ROWS_PER_PAGE = (3, 5, 8, 10)
ALLOWED_NUMBER_STYLES = ("raw", "dot")
# full: 問題と解答 / question: 問題のみ(解答欄は空白) / blank: 白紙(罫線のみ)
ALLOWED_PRINT_MODES = ("full", "question", "blank")
ALLOWED_FONT_SIZES = ("sm", "md", "lg")
FONT_SIZE_MULTIPLIERS = {
    "sm": 0.82,
    "md": 1.0,
    "lg": 1.22,
}
HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")
MAX_ROWS = 2000
MAX_PAGES = 120
MAX_FIELD_LEN = 2000
MAX_TITLE_LEN = 80
DEFAULT_TITLE = "BlindCardMaker"
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
EMBEDDED_FONT_PATH = os.path.join(FONT_DIR, "ipaexm.ttf")
CID_FONT_NAME = "HeiseiMin-W3"
EMBEDDED_FONT_NAME = "AnkiMincho"
FONT_NAME = CID_FONT_NAME
COPYRIGHT_TEXT = "© BlindCardMaker"
PLAIN_SECTION_KEY = ""
ROW_TEXT_HEIGHT_RATIO = 0.9
SPLIT_RATIO = 0.58

_FONT_REGISTERED = False
_STYLE_SEQ = 0


def _ensure_font() -> None:
    global _FONT_REGISTERED, FONT_NAME
    if _FONT_REGISTERED:
        return
    if os.path.isfile(EMBEDDED_FONT_PATH):
        pdfmetrics.registerFont(TTFont(EMBEDDED_FONT_NAME, EMBEDDED_FONT_PATH))
        FONT_NAME = EMBEDDED_FONT_NAME
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(CID_FONT_NAME))
        FONT_NAME = CID_FONT_NAME
    _FONT_REGISTERED = True


def _clip_text(value: object, max_len: int = MAX_FIELD_LEN) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _safe_text(value: object) -> str:
    return escape(_clip_text(value))


def _section_key(num: str) -> str:
    """ハイフン付き番号だけをセクションキーにする。連番は同一グループ。"""
    raw = (num or "").strip()
    if "-" not in raw:
        return PLAIN_SECTION_KEY
    prefix = raw.split("-", 1)[0].strip()
    return prefix


def _section_label(section_key: str) -> str:
    return section_key or "1"


def _group_rows(rows: Sequence[Mapping[str, str]]) -> list[tuple[str, list[dict[str, str]]]]:
    groups: list[tuple[str, list[dict[str, str]]]] = []
    for row in rows:
        key = _section_key(row.get("num", ""))
        if not groups or groups[-1][0] != key:
            groups.append((key, [dict(row)]))
        else:
            groups[-1][1].append(dict(row))
    return groups


def estimate_pages(data: Iterable[Mapping], rows_per_page: int = 5) -> int:
    rows = _normalize_rows(data, enforce_limit=False)
    if not rows or rows_per_page <= 0:
        return 0
    pages = 0
    for _, group in _group_rows(rows):
        pages += (len(group) + rows_per_page - 1) // rows_per_page
    return pages


def _normalize_rows(
    data: Iterable[Mapping],
    enforce_limit: bool = True,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    total = 0
    for item in data:
        if not isinstance(item, Mapping):
            continue
        num = _clip_text(item.get("num", ""))
        question = _safe_text(item.get("question", ""))
        answer = _safe_text(item.get("answer", ""))
        note = _safe_text(item.get("note", ""))
        if not (num or question or answer or note):
            continue
        total += 1
        if len(rows) < MAX_ROWS:
            rows.append(
                {
                    "num": num,
                    "question": question,
                    "answer": answer,
                    "note": note,
                }
            )
    if enforce_limit and total > MAX_ROWS:
        raise ValueError(
            f"データが{total}件あります。一度に出力できるのは{MAX_ROWS}件までです。"
        )
    return rows


def _plain_text(value: object, max_len: int) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _display_number(raw_num: str, page_index: int, number_style: str) -> str:
    if number_style == "dot":
        return f"{page_index + 1}."
    return (raw_num or "").strip()


def _fit_text(canvas_obj: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> str:
    if max_width <= 0 or canvas_obj.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and canvas_obj.stringWidth(trimmed + ellipsis, font, size) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _clone_style(base: ParagraphStyle, font_size: float, leading: float) -> ParagraphStyle:
    global _STYLE_SEQ
    _STYLE_SEQ += 1
    return ParagraphStyle(
        f"{base.name}_fit_{_STYLE_SEQ}",
        parent=base,
        fontSize=font_size,
        leading=leading,
    )


def _wrap_paragraph(text: str, style: ParagraphStyle, max_width: float) -> tuple[Paragraph, float]:
    paragraph = Paragraph(text or " ", style)
    _, height = paragraph.wrap(max_width, 10000)
    return paragraph, height


def _fit_paragraph(
    text: str,
    style: ParagraphStyle,
    max_width: float,
    max_height: float,
    min_scale: float = 0.55,
) -> tuple[Paragraph, float]:
    """行高に収まる Paragraph を返す。必要なら縮小し、それでもダメなら省略する。"""
    source = text or " "
    usable_height = max(max_height, 1.0)
    paragraph, height = _wrap_paragraph(source, style, max_width)
    if height <= usable_height:
        return paragraph, height

    ratio = max(min_scale, (usable_height / height) * 0.96)
    fitted = _clone_style(
        style,
        max(4.5, style.fontSize * ratio),
        max(5.5, style.leading * ratio),
    )
    paragraph, height = _wrap_paragraph(source, fitted, max_width)
    if height <= usable_height:
        return paragraph, height

    lo, hi = 0, len(source)
    best = Paragraph("…", fitted)
    best_h = usable_height
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = source if mid >= len(source) else (source[:mid] + "…")
        paragraph, height = _wrap_paragraph(candidate, fitted, max_width)
        if height <= usable_height:
            best, best_h = paragraph, height
            lo = mid + 1
        else:
            hi = mid - 1
    return best, best_h


def _normalize_font_size(value: object, label: str) -> str:
    size_label = str(value or "md").strip().lower()
    if size_label not in ALLOWED_FONT_SIZES:
        raise ValueError(f"{label}は 小 / 標準 / 大 のいずれかを指定してください。")
    return size_label


def validate_options(
    paper_size: str,
    rows_per_page: int,
    answer_color: str,
    title: str = "",
    show_checkbox: object = False,
    number_style: str = "raw",
    print_mode: str = "full",
    question_font_size: str | None = None,
    answer_font_size: str | None = None,
    font_size: str | None = None,
) -> tuple[str, int, str, str, bool, str, str, str, str]:
    size_key = str(paper_size or "A6").upper()
    if size_key not in PAGE_SIZES:
        raise ValueError("用紙サイズは A6 / A5 / A4 のいずれかを指定してください。")

    try:
        rows = int(rows_per_page)
    except (TypeError, ValueError) as exc:
        raise ValueError("1ページの行数が不正です。") from exc
    if rows not in ALLOWED_ROWS_PER_PAGE:
        raise ValueError("1ページの行数は 3 / 5 / 8 / 10 のいずれかを指定してください。")

    color = str(answer_color or "#FFA500").strip()
    if not HEX_COLOR_RE.match(color):
        raise ValueError("解答色は #RRGGBB 形式で指定してください。")

    heading = _plain_text(title, MAX_TITLE_LEN) or DEFAULT_TITLE
    style = str(number_style or "raw").strip().lower()
    if style not in ALLOWED_NUMBER_STYLES:
        raise ValueError("番号の表記は 入力どおり / 1. 2. 3. のいずれかを指定してください。")

    mode = str(print_mode or "full").strip().lower()
    if mode not in ALLOWED_PRINT_MODES:
        raise ValueError("印刷する内容は 問題と解答 / 問題のみ / 白紙 のいずれかを指定してください。")

    shared = font_size
    q_size = question_font_size if question_font_size not in (None, "") else shared
    a_size = answer_font_size if answer_font_size not in (None, "") else shared
    question_label = _normalize_font_size(q_size, "問題の文字サイズ")
    answer_label = _normalize_font_size(a_size, "解答の文字サイズ")

    return (
        size_key,
        rows,
        color.upper(),
        heading,
        _truthy(show_checkbox),
        style,
        mode,
        question_label,
        answer_label,
    )


def generate_anki_pdf(
    data: Sequence[Mapping],
    paper_size: str = "A6",
    rows_per_page: int = 5,
    answer_color: str = "#FFA500",
    title: str = "",
    show_checkbox: object = False,
    number_style: str = "raw",
    print_mode: str = "full",
    question_font_size: str | None = None,
    answer_font_size: str | None = None,
    font_size: str | None = None,
    first_page_only: object = False,
) -> bytes:
    """暗記カード PDF を生成し、バイト列で返す。"""
    (
        paper_size,
        rows_per_page,
        answer_color,
        title,
        show_checkbox,
        number_style,
        print_mode,
        question_font_size,
        answer_font_size,
    ) = validate_options(
        paper_size,
        rows_per_page,
        answer_color,
        title=title,
        show_checkbox=show_checkbox,
        number_style=number_style,
        print_mode=print_mode,
        question_font_size=question_font_size,
        answer_font_size=answer_font_size,
        font_size=font_size,
    )
    preview_one = _truthy(first_page_only)
    rows = _normalize_rows(data)
    if not rows:
        if print_mode != "blank":
            raise ValueError("出力するデータがありません。番号・問題・解答のいずれかを入力してください。")
        # 白紙モードはデータなしでも1ページ分の罫線を出す
        rows = [{"num": "", "question": "", "answer": "", "note": ""} for _ in range(rows_per_page)]

    if not preview_one:
        page_total = 0
        for _, group in _group_rows(rows):
            page_total += (len(group) + rows_per_page - 1) // rows_per_page
        if page_total > MAX_PAGES:
            raise ValueError(
                f"出力が{page_total}ページになります。一度に出せるのは{MAX_PAGES}ページまでです。"
                "1ページの行数を増やすか、CSVを分割してください。"
            )

    _ensure_font()
    width, height = PAGE_SIZES[paper_size]
    scale = width / A6[0]

    left_margin = 22 * scale
    right_margin = 16 * scale
    top_margin = 24 * scale
    bottom_margin = 17 * scale
    header_height = 18 * scale

    content_width = width - left_margin - right_margin
    content_height = height - top_margin - bottom_margin - header_height
    row_h = content_height / rows_per_page
    # 解答は2〜4文字で収まることが多く、半々にすると右が大きく余る。
    # 問題側を広げて折り返しを減らし、解答側は書き込める幅を残す。
    split_x = left_margin + (content_width * SPLIT_RATIO)

    row_scale = max(0.75, min(row_h / 68.0, 2.2))
    q_mult = FONT_SIZE_MULTIPLIERS[question_font_size]
    a_mult = FONT_SIZE_MULTIPLIERS[answer_font_size]
    font_scale = row_scale
    q_size = 9 * row_scale * q_mult
    a_size = 10.5 * row_scale * a_mult
    note_size = 7.5 * row_scale * a_mult
    num_size = 7 * row_scale * q_mult
    header_size = 8 * row_scale
    page_label_size = 7 * row_scale
    copy_size = 6.5 * row_scale

    styles = getSampleStyleSheet()
    left_style = ParagraphStyle(
        "LeftColStyle",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=q_size,
        leading=q_size * 1.33,
        textColor=colors.HexColor("#111111"),
        wordWrap="CJK",
    )
    ans_style = ParagraphStyle(
        "AnsStyle",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=a_size,
        leading=a_size * 1.24,
        textColor=colors.HexColor(answer_color),
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "NoteStyle",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=note_size,
        leading=note_size * 1.27,
        textColor=colors.HexColor("#666666"),
        wordWrap="CJK",
    )

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZES[paper_size])
    page_num = 1

    for section_id, group in _group_rows(rows):
        group_page_count = (len(group) + rows_per_page - 1) // rows_per_page
        for gp in range(group_page_count):
            chunk = group[gp * rows_per_page : (gp + 1) * rows_per_page]

            header_text = f"{title} - NO.{_section_label(section_id)}"
            page_label = f"PAGE: {page_num}"
            header_y = height - top_margin + (5 * scale)

            c.setFont("Helvetica", page_label_size)
            page_label_w = c.stringWidth(page_label, "Helvetica", page_label_size)
            title_max_w = (width - right_margin - left_margin) - page_label_w - (10 * scale)

            c.setFont(FONT_NAME, header_size)
            c.setFillColor(colors.HexColor("#333333"))
            c.drawString(
                left_margin,
                header_y,
                _fit_text(c, header_text, FONT_NAME, header_size, title_max_w),
            )

            c.setFont("Helvetica", page_label_size)
            c.setFillColor(colors.HexColor("#666666"))
            c.drawRightString(
                width - right_margin,
                header_y,
                page_label,
            )

            c.setLineWidth(1.5 * scale)
            c.setStrokeColor(colors.HexColor("#222222"))
            c.line(left_margin, height - top_margin, width - right_margin, height - top_margin)

            for i in range(rows_per_page):
                row_y_top = height - top_margin - header_height - (i * row_h)
                row_y_bottom = row_y_top - row_h

                c.setLineWidth(0.5 * scale)
                c.setStrokeColor(colors.HexColor("#CCCCCC"))
                c.setDash([2, 2], 0)
                c.line(left_margin, row_y_bottom, width - right_margin, row_y_bottom)
                c.setDash([], 0)

                c.setLineWidth(0.8 * scale)
                c.setStrokeColor(colors.HexColor("#222222"))
                c.line(split_x, row_y_bottom, split_x, row_y_top)

                if i >= len(chunk):
                    continue

                row = chunk[i]
                if print_mode == "blank":
                    # 罫線とチェック欄だけを残し、文字はすべて出さない
                    num = q_text = a_text = note_text = ""
                else:
                    num = _display_number(row["num"], i, number_style)
                    q_text = row["question"]
                    a_text = row["answer"] if print_mode == "full" else ""
                    note_text = row["note"] if print_mode == "full" else ""

                label_x = left_margin
                num_y = row_y_top - (16 * font_scale)

                if show_checkbox:
                    box = max(6.5 * font_scale, 7.0 * scale)
                    box_y = num_y - (1.2 * scale)
                    c.setLineWidth(0.75 * scale)
                    c.setStrokeColor(colors.HexColor("#444444"))
                    c.rect(label_x, box_y, box, box, stroke=1, fill=0)
                    label_x += box + (3.2 * scale)

                if num:
                    c.setFont(FONT_NAME, num_size)
                    c.setFillColor(colors.HexColor("#777777"))
                    c.drawString(label_x, num_y, num)
                    num_w = c.stringWidth(num, FONT_NAME, num_size) + (3 * scale)
                    text_left = label_x + num_w
                else:
                    text_left = label_x + (2 * scale)
                max_q_width = (split_x - (8 * scale)) - text_left
                if max_q_width < 12:
                    max_q_width = 12

                text_h = row_h * ROW_TEXT_HEIGHT_RATIO
                p_q, h_q = _fit_paragraph(q_text, left_style, max_q_width, text_h)
                p_q.drawOn(c, text_left, row_y_bottom + ((row_h - h_q) / 2))

                max_a_width = (width - right_margin) - (split_x + (8 * scale))
                if max_a_width < 12:
                    max_a_width = 12

                gap = 2 * font_scale
                if note_text:
                    p_a, h_a = _fit_paragraph(a_text, ans_style, max_a_width, text_h)
                    p_note, h_n = _fit_paragraph(note_text, note_style, max_a_width, text_h)
                    total_h = h_a + h_n + gap
                    if total_h > text_h:
                        avail = max(text_h - gap, 1.0)
                        a_share = avail * (h_a / total_h)
                        n_share = avail * (h_n / total_h)
                        p_a, h_a = _fit_paragraph(a_text, ans_style, max_a_width, a_share)
                        p_note, h_n = _fit_paragraph(note_text, note_style, max_a_width, n_share)
                        total_h = h_a + h_n + gap
                    start_y = row_y_bottom + ((row_h - total_h) / 2) + h_n + gap
                    p_a.drawOn(c, split_x + (8 * scale), start_y)
                    p_note.drawOn(c, split_x + (8 * scale), start_y - h_n - gap)
                else:
                    p_a, h_a = _fit_paragraph(a_text, ans_style, max_a_width, text_h)
                    p_a.drawOn(c, split_x + (8 * scale), row_y_bottom + ((row_h - h_a) / 2))

            c.setFont("Helvetica", copy_size)
            c.setFillColor(colors.HexColor("#888888"))
            c.drawCentredString(width / 2.0, 10 * scale, COPYRIGHT_TEXT)

            c.showPage()
            page_num += 1
            if preview_one:
                c.save()
                return buffer.getvalue()

    c.save()
    return buffer.getvalue()
