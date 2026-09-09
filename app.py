"""BlindCardMaker — Flask エントリポイント。"""

from __future__ import annotations

import hashlib
import io
import os
import random
import tempfile
import time
from collections import deque
from threading import Lock, Semaphore

try:
    import fcntl  # POSIX のみ。無い環境ではプロセス内カウンタにフォールバックする。
except ImportError:  # pragma: no cover
    fcntl = None

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from pdf_generator import generate_anki_pdf, validate_options

GENERATE_RATE = (12, 60.0)
PREVIEW_RATE = (180, 60.0)
PDF_CONCURRENCY = 2
PDF_WAIT_SECONDS = 20.0

_RATE_LOCK = Lock()
_RATE_HITS: dict[str, deque[float]] = {}
_PDF_SLOT = Semaphore(PDF_CONCURRENCY)

# CGI ではリクエストごとにプロセスが作り直されるため、プロセス内のカウンタでは
# レート制限が一切効かない。ファイル＋flock でプロセスをまたいで数える。
RATE_STATE_DIR = os.environ.get("RATE_STATE_DIR") or os.path.join(
    tempfile.gettempdir(), "blindcard-rate"
)
_RATE_PRUNE_PROBABILITY = 0.02


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _app_prefix() -> str:
    raw = os.environ.get("APPLICATION_ROOT", "").strip()
    if not raw or raw == "/":
        return ""
    return "/" + raw.strip("/")


APP_PREFIX = _app_prefix()
DEBUG = _env_flag("ANKI_DEBUG")
TRUST_PROXY = _env_flag("TRUST_PROXY")


class PrefixMiddleware:
    """SCRIPT_NAME を固定し、パスにプレフィックスが付いていれば剥がす。"""

    def __init__(self, wsgi_app, prefix: str):
        self.wsgi_app = wsgi_app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or "/"
        prefix = self.prefix
        environ["SCRIPT_NAME"] = prefix
        if path == prefix or path.startswith(prefix + "/"):
            rest = path[len(prefix) :] or "/"
            if not rest.startswith("/"):
                rest = "/" + rest
            environ["PATH_INFO"] = rest
        return self.wsgi_app(environ, start_response)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = DEBUG
app.jinja_env.auto_reload = DEBUG
app.config["APPLICATION_ROOT"] = APP_PREFIX or "/"

if TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)
if APP_PREFIX:
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, APP_PREFIX)


@app.context_processor
def inject_prefix():
    return {"prefix": request.script_root or APP_PREFIX}


@app.after_request
def add_security_headers(response):
    if request.path in {"/", "/guide", "/app.js", "/static/app.css"}:
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    if request.path in {"/", "/guide"}:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            # Vue のグローバルビルドは DOM 上のテンプレートを new Function で
            # コンパイルするため 'unsafe-eval' が必須（外すと画面が起動しない）
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-src blob:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/guide")
def guide():
    return render_template("guide.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon")


@app.get("/vue.global.prod.js")
def vue_lib():
    return send_from_directory(app.template_folder, "vue.global.prod.js")


@app.get("/app.js")
def app_js():
    return send_from_directory(app.template_folder, "app.js")


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "送信データが大きすぎます。件数を減らすか、CSVを分割してください。"}), 413


def _client_ip() -> str:
    return (request.remote_addr or "unknown")[:64]


def _rate_ok_in_memory(bucket_key: str, limit: int, window: float) -> bool:
    """常駐プロセス用。CGI では毎回リセットされるので単体では使えない。"""
    now = time.monotonic()
    with _RATE_LOCK:
        hits = _RATE_HITS.setdefault(bucket_key, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        if len(_RATE_HITS) > 5000:
            stale = [key for key, values in _RATE_HITS.items() if not values or now - values[-1] > window]
            for key in stale[:2500]:
                _RATE_HITS.pop(key, None)
        return True


def _rate_state_path(bucket_key: str) -> str:
    name = hashlib.sha256(bucket_key.encode("utf-8")).hexdigest()[:32]
    return os.path.join(RATE_STATE_DIR, name)


def _prune_rate_state(window: float) -> None:
    """取りこぼしたカウンタファイルを間引く。失敗しても無視する。"""
    cutoff = time.time() - max(window * 4, 300)
    try:
        with os.scandir(RATE_STATE_DIR) as entries:
            for entry in entries:
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        os.unlink(entry.path)
                except OSError:
                    continue
    except OSError:
        pass


def _rate_ok_on_disk(bucket_key: str, limit: int, window: float) -> bool:
    """ファイル＋flock で数える。CGI でもワーカー並列でも共有される。"""
    now = time.time()
    path = _rate_state_path(bucket_key)
    try:
        os.makedirs(RATE_STATE_DIR, mode=0o700, exist_ok=True)
        with open(path, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.seek(0)
                hits = []
                for token in fh.read().split():
                    try:
                        stamp = float(token)
                    except ValueError:
                        continue
                    if now - stamp <= window:
                        hits.append(stamp)
                allowed = len(hits) < limit
                if allowed:
                    hits.append(now)
                fh.seek(0)
                fh.truncate()
                fh.write(" ".join("%.3f" % stamp for stamp in hits[-limit:]))
                fh.flush()
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        app.logger.warning("レート制限の状態を保存できません (%s): %s", RATE_STATE_DIR, exc)
        return _rate_ok_in_memory(bucket_key, limit, window)

    if random.random() < _RATE_PRUNE_PROBABILITY:
        _prune_rate_state(window)
    return allowed


def _rate_ok(bucket_key: str, limit: int, window: float) -> bool:
    if app.config.get("TESTING"):
        return True
    if fcntl is None:
        return _rate_ok_in_memory(bucket_key, limit, window)
    return _rate_ok_on_disk(bucket_key, limit, window)


def _pdf_from_payload(payload: dict, first_page_only: bool = False) -> tuple[bytes, str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise TypeError("data")
    shared = payload.get("fontSize")
    paper_size, *_rest = validate_options(
        payload.get("paperSize", "A6"),
        payload.get("rowsPerPage", 5),
        payload.get("color", "#FFA500"),
        title=payload.get("title", ""),
        show_checkbox=payload.get("showCheckbox", False),
        number_style=payload.get("numberStyle", "raw"),
        print_mode=payload.get("printMode", "full"),
        question_font_size=payload.get("questionFontSize") or shared,
        answer_font_size=payload.get("answerFontSize") or shared,
    )
    pdf_bytes = generate_anki_pdf(
        data=data,
        paper_size=payload.get("paperSize", "A6"),
        rows_per_page=payload.get("rowsPerPage", 5),
        answer_color=payload.get("color", "#FFA500"),
        title=payload.get("title", ""),
        show_checkbox=payload.get("showCheckbox", False),
        number_style=payload.get("numberStyle", "raw"),
        print_mode=payload.get("printMode", "full"),
        question_font_size=payload.get("questionFontSize") or shared,
        answer_font_size=payload.get("answerFontSize") or shared,
        first_page_only=first_page_only,
    )
    return pdf_bytes, paper_size


def _pdf_response(payload: dict, *, as_attachment: bool, first_page_only: bool):
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON 形式で送信してください。"}), 400
    if not isinstance(payload.get("data"), list):
        return jsonify({"error": "data は配列で送信してください。"}), 400

    kind = "preview" if first_page_only else "generate"
    limit, window = PREVIEW_RATE if first_page_only else GENERATE_RATE
    if not _rate_ok(f"{kind}:{_client_ip()}", limit, window):
        body = jsonify({"error": "アクセスが集中しています。少し待ってからやり直してください。"})
        return body, 429, {"Retry-After": "20"}

    testing = bool(app.config.get("TESTING"))
    acquired = True if testing else _PDF_SLOT.acquire(timeout=PDF_WAIT_SECONDS)
    if not acquired:
        return jsonify({"error": "サーバーが混み合っています。少し待ってからやり直してください。"}), 503

    try:
        pdf_bytes, paper = _pdf_from_payload(payload, first_page_only=first_page_only)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("PDF 生成に失敗しました")
        return jsonify({"error": "PDF の生成中にエラーが発生しました。"}), 500
    finally:
        if not testing:
            _PDF_SLOT.release()

    filename = (
        f"anki_preview_{paper.lower()}.pdf"
        if first_page_only
        else f"anki_notebook_{paper.lower()}.pdf"
    )
    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=as_attachment,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _read_json_payload():
    """壊れた JSON や深すぎるネスト（RecursionError）でも 500 にしない。"""
    try:
        return request.get_json(silent=True)
    except HTTPException:
        raise  # 413 などはそのまま Flask のハンドラに処理させる
    except Exception:
        return None


@app.post("/api/generate-pdf")
def api_generate_pdf():
    return _pdf_response(_read_json_payload(), as_attachment=True, first_page_only=False)


@app.post("/api/preview-pdf")
def api_preview_pdf():
    return _pdf_response(_read_json_payload(), as_attachment=False, first_page_only=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=DEBUG)
