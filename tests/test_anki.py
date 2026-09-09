"""連番CSVのページ数、用紙スケール、APIバリデーション。"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from make_pdf import read_anki_csv
from pdf_generator import (
    EMBEDDED_FONT_PATH,
    MAX_PAGES,
    _normalize_rows,
    estimate_pages,
    generate_anki_pdf,
    validate_options,
)

app.config["TESTING"] = True


def _rows(nums, question="問題", answer="解答"):
    return [{"num": str(num), "question": question, "answer": answer, "note": ""} for num in nums]


def _pdf_page_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)\b", pdf_bytes))


def _mediabox(pdf_bytes: bytes) -> tuple[float, float]:
    match = re.search(
        rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]",
        pdf_bytes,
    )
    if not match:
        raise AssertionError("MediaBox が見つかりません")
    return float(match.group(3)), float(match.group(4))


class PdfPagingTests(unittest.TestCase):
    def test_sequential_numbers_share_pages(self):
        data = _rows(range(1, 11))
        self.assertEqual(estimate_pages(data, 5), 2)
        pdf = generate_anki_pdf(data, paper_size="A6", rows_per_page=5)
        self.assertEqual(_pdf_page_count(pdf), 2)

    def test_hyphen_sections_still_split(self):
        data = _rows([f"1-{i}" for i in range(1, 6)] + [f"2-{i}" for i in range(1, 6)])
        self.assertEqual(estimate_pages(data, 5), 2)
        pdf = generate_anki_pdf(data, paper_size="A6", rows_per_page=5)
        self.assertEqual(_pdf_page_count(pdf), 2)

    def test_interleaved_sections_are_consecutive(self):
        data = _rows(["1-1", "2-1", "1-2", "2-2"])
        self.assertEqual(estimate_pages(data, 5), 4)

    def test_blank_numbers_do_not_split(self):
        data = _rows([""] * 10)
        self.assertEqual(estimate_pages(data, 5), 2)


class PdfContentTests(unittest.TestCase):
    def test_number_keeps_ampersand(self):
        rows = _normalize_rows(
            [{"num": "小1&2", "question": "A&B", "answer": "<x>", "note": "C>D"}]
        )
        self.assertEqual(rows[0]["num"], "小1&2")
        self.assertEqual(rows[0]["question"], "A&amp;B")
        self.assertEqual(rows[0]["answer"], "&lt;x&gt;")
        self.assertEqual(rows[0]["note"], "C&gt;D")
        pdf = generate_anki_pdf(
            [{"num": "小1&2", "question": "A&B", "answer": "<x>", "note": "C>D"}],
            paper_size="A6",
            rows_per_page=5,
        )
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_long_text_does_not_raise(self):
        data = [{"num": "1-1", "question": "あ" * 150, "answer": "い" * 80, "note": "う" * 80}]
        pdf = generate_anki_pdf(data, paper_size="A6", rows_per_page=10)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_too_many_rows_are_rejected(self):
        data = _rows(range(1, 2002))
        with self.assertRaises(ValueError) as ctx:
            generate_anki_pdf(data)
        self.assertIn("2000", str(ctx.exception))

    def test_too_many_pages_are_rejected(self):
        data = _rows([f"{i}-1" for i in range(1, MAX_PAGES + 10)])
        with self.assertRaises(ValueError) as ctx:
            generate_anki_pdf(data, paper_size="A6", rows_per_page=5)
        self.assertIn(str(MAX_PAGES), str(ctx.exception))
        preview = generate_anki_pdf(
            data, paper_size="A6", rows_per_page=5, first_page_only=True
        )
        self.assertEqual(_pdf_page_count(preview), 1)

    def test_paper_scale_a6_a5_a4(self):
        data = _rows(["1-1"])
        a6 = generate_anki_pdf(data, paper_size="A6")
        a5 = generate_anki_pdf(data, paper_size="A5")
        a4 = generate_anki_pdf(data, paper_size="A4")
        w6, h6 = _mediabox(a6)
        w5, h5 = _mediabox(a5)
        w4, h4 = _mediabox(a4)
        self.assertLess(w6, w5)
        self.assertLess(w5, w4)
        self.assertLess(h6, h5)
        self.assertLess(h5, h4)

    def test_invalid_options(self):
        with self.assertRaises(ValueError):
            validate_options("B5", 5, "#FFA500")
        with self.assertRaises(ValueError):
            validate_options("A6", 7, "#FFA500")
        with self.assertRaises(ValueError):
            validate_options("A6", 5, "orange")
        with self.assertRaises(ValueError):
            validate_options("A6", 5, "#FFA500", font_size="huge")
        with self.assertRaises(ValueError):
            validate_options("A6", 5, "#FFA500", question_font_size="huge")
        with self.assertRaises(ValueError):
            validate_options("A6", 5, "#FFA500", answer_font_size="huge")

    def test_font_size_presets_generate(self):
        data = _rows(["1-1"])
        for size in ("sm", "md", "lg"):
            pdf = generate_anki_pdf(data, paper_size="A6", font_size=size)
            self.assertTrue(pdf.startswith(b"%PDF"), size)

    def test_question_and_answer_font_sizes_differ(self):
        data = _rows(["1-1"], question="問題文を少し長めに書く", answer="解答")
        q_lg = generate_anki_pdf(data, question_font_size="lg", answer_font_size="sm")
        a_lg = generate_anki_pdf(data, question_font_size="sm", answer_font_size="lg")
        self.assertTrue(q_lg.startswith(b"%PDF"))
        self.assertTrue(a_lg.startswith(b"%PDF"))
        self.assertNotEqual(q_lg, a_lg)

    def test_first_page_only_is_one_page(self):
        data = _rows(range(1, 16))
        full = generate_anki_pdf(data, paper_size="A6", rows_per_page=5)
        preview = generate_anki_pdf(data, paper_size="A6", rows_per_page=5, first_page_only=True)
        self.assertEqual(_pdf_page_count(full), 3)
        self.assertEqual(_pdf_page_count(preview), 1)

    def test_japanese_font_is_embedded(self):
        self.assertTrue(os.path.isfile(EMBEDDED_FONT_PATH))
        pdf = generate_anki_pdf(_rows(["1-1"]))
        self.assertIn(b"/FontFile2", pdf)


class CsvEncodingTests(unittest.TestCase):
    def test_cp932_csv(self):
        raw = "番号,問題,解答\n1,絶好のキカイ,機会\n".encode("cp932")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sjis.csv"
            path.write_bytes(raw)
            df = read_anki_csv(str(path))
        self.assertEqual(str(df.iloc[0, 1]), "絶好のキカイ")
        self.assertEqual(str(df.iloc[0, 2]), "機会")


class PrintModeTests(unittest.TestCase):
    def test_modes_generate_pdf(self):
        data = _rows([f"1-{i}" for i in range(1, 8)])
        for mode in ("full", "question", "blank"):
            pdf = generate_anki_pdf(data, paper_size="A6", rows_per_page=5, print_mode=mode)
            self.assertTrue(pdf.startswith(b"%PDF"), mode)
            self.assertEqual(_pdf_page_count(pdf), 2, mode)

    def test_hidden_content_makes_smaller_pdf(self):
        data = _rows([f"1-{i}" for i in range(1, 8)], question="問題文", answer="解答")
        full = len(generate_anki_pdf(data, print_mode="full"))
        question = len(generate_anki_pdf(data, print_mode="question"))
        blank = len(generate_anki_pdf(data, print_mode="blank"))
        self.assertLess(question, full)
        self.assertLess(blank, question)

    def test_blank_mode_works_without_data(self):
        pdf = generate_anki_pdf([], paper_size="A6", rows_per_page=5, print_mode="blank")
        self.assertEqual(_pdf_page_count(pdf), 1)

    def test_other_modes_still_require_data(self):
        for mode in ("full", "question"):
            with self.assertRaises(ValueError):
                generate_anki_pdf([], print_mode=mode)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_anki_pdf(_rows(["1-1"]), print_mode="secret")


class ApiValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_invalid_color_returns_400(self):
        res = self.client.post(
            "/api/generate-pdf",
            json={
                "paperSize": "A6",
                "rowsPerPage": 5,
                "color": "red",
                "data": [{"num": "1-1", "question": "q", "answer": "a", "note": ""}],
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_invalid_rows_returns_400(self):
        res = self.client.post(
            "/api/generate-pdf",
            json={
                "paperSize": "A6",
                "rowsPerPage": 7,
                "color": "#FFA500",
                "data": [{"num": "1-1", "question": "q", "answer": "a", "note": ""}],
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_payload_too_large_returns_json(self):
        previous = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 64
        try:
            res = self.client.post(
                "/api/generate-pdf",
                data=b'{"paperSize":"A6","data":[]}' + (b" " * 80),
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 413)
            self.assertEqual(res.mimetype, "application/json")
            self.assertIn("error", res.get_json())
        finally:
            app.config["MAX_CONTENT_LENGTH"] = previous

    def test_ok_pdf(self):
        res = self.client.post(
            "/api/generate-pdf",
            json={
                "paperSize": "A5",
                "rowsPerPage": 5,
                "color": "#FFA500",
                "data": [{"num": "1", "question": "q", "answer": "a", "note": ""}],
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/pdf")
        self.assertTrue(res.data.startswith(b"%PDF"))

    def test_preview_returns_first_page_only(self):
        res = self.client.post(
            "/api/preview-pdf",
            json={
                "paperSize": "A6",
                "rowsPerPage": 5,
                "color": "#FFA500",
                "questionFontSize": "lg",
                "answerFontSize": "sm",
                "data": [
                    {"num": str(i), "question": "q", "answer": "a", "note": ""}
                    for i in range(1, 12)
                ],
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/pdf")
        self.assertTrue(res.data.startswith(b"%PDF"))
        self.assertEqual(_pdf_page_count(res.data), 1)
        self.assertNotIn("attachment", (res.headers.get("Content-Disposition") or "").lower())

    def test_pathlike_paper_size_is_rejected(self):
        res = self.client.post(
            "/api/generate-pdf",
            json={
                "paperSize": "../evil",
                "rowsPerPage": 5,
                "color": "#FFA500",
                "data": [{"num": "1-1", "question": "q", "answer": "a", "note": ""}],
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("evil", (res.headers.get("Content-Disposition") or "").lower())

    def test_generate_rate_limit(self):
        import app as app_mod

        previous_testing = app.config.get("TESTING")
        previous_rate = app_mod.GENERATE_RATE
        app.config["TESTING"] = False
        app_mod.GENERATE_RATE = (1, 60.0)
        app_mod._RATE_HITS.clear()
        payload = {
            "paperSize": "A6",
            "rowsPerPage": 5,
            "color": "#FFA500",
            "data": [{"num": "1", "question": "q", "answer": "a", "note": ""}],
        }
        try:
            first = self.client.post("/api/generate-pdf", json=payload)
            self.assertEqual(first.status_code, 200)
            second = self.client.post("/api/generate-pdf", json=payload)
            self.assertEqual(second.status_code, 429)
            self.assertEqual(second.mimetype, "application/json")
        finally:
            app.config["TESTING"] = previous_testing
            app_mod.GENERATE_RATE = previous_rate
            app_mod._RATE_HITS.clear()


class PageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_links_to_guide(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("BlindCardMaker", html)
        self.assertIn("/static/blindcard-maker.svg", html)
        self.assertIn('rel="icon"', html)
        self.assertIn('href="/guide"', html)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("default-src 'self'", res.headers.get("Content-Security-Policy", ""))

    def test_guide_page(self):
        res = self.client.get("/guide")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("使い方", html)
        self.assertIn("BlindCardMaker", html)
        self.assertIn("/static/blindcard-maker.svg", html)
        self.assertIn('rel="icon"', html)
        self.assertIn("赤シート", html)
        self.assertIn("CSVの書き方", html)
        self.assertIn('href="/"', html)
        self.assertIn("サーバーに保存しません", html)
        self.assertIn("120ページ", html)
        self.assertIn("IPAex明朝", html)


if __name__ == "__main__":
    unittest.main()
