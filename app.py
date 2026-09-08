"""BlindCardMaker — Flask エントリポイント。"""

from __future__ import annotations

import io
import os

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

from pdf_generator import generate_anki_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True


@app.after_request
def disable_template_cache(response):
    if request.path in {"/", "/guide", "/app.js", "/static/app.css"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/guide")
def guide():
    return render_template("guide.html")


@app.get("/vue.global.prod.js")
def vue_lib():
    return send_from_directory(app.template_folder, "vue.global.prod.js")


@app.get("/app.js")
def app_js():
    return send_from_directory(app.template_folder, "app.js")


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "送信データが大きすぎます。件数を減らすか、CSVを分割してください。"}), 413


@app.post("/api/generate-pdf")
def api_generate_pdf():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON 形式で送信してください。"}), 400

    data = payload.get("data")
    if not isinstance(data, list):
        return jsonify({"error": "data は配列で送信してください。"}), 400

    try:
        pdf_bytes = generate_anki_pdf(
            data=data,
            paper_size=payload.get("paperSize", "A6"),
            rows_per_page=payload.get("rowsPerPage", 5),
            answer_color=payload.get("color", "#FFA500"),
            title=payload.get("title", ""),
            show_checkbox=payload.get("showCheckbox", False),
            number_style=payload.get("numberStyle", "raw"),
            print_mode=payload.get("printMode", "full"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("PDF 生成に失敗しました")
        return jsonify({"error": "PDF の生成中にエラーが発生しました。"}), 500

    paper = str(payload.get("paperSize", "A6")).upper()
    filename = f"anki_notebook_{paper.lower()}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    debug = os.environ.get("ANKI_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host="127.0.0.1", port=5000, debug=debug)
