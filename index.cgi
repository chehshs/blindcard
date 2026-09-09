#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
"""CGI 入口。常駐プロセスを置けない共有サーバー向けに、リクエストごとに起動する。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# pip install --user の置き場は Python のバージョンで変わるので固定しない。
_user_site = os.path.expanduser(
    "~/.local/lib/python%d.%d/site-packages" % (sys.version_info[0], sys.version_info[1])
)
if os.path.isdir(_user_site) and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

os.environ["APPLICATION_ROOT"] = "/tools/blindcard"
# 前段にリバースプロキシが無い構成では REMOTE_ADDR がそのまま client の IP。
# ここで X-Forwarded-For を信用すると、ヘッダーを付けるだけでレート制限を回避できる。
os.environ["TRUST_PROXY"] = "0"
os.environ.pop("ANKI_DEBUG", None)
# レート制限のカウンタ置き場。書けない場合はプロセス内カウンタに落ちる。
os.environ.setdefault("RATE_STATE_DIR", os.path.join(ROOT, ".rate-state"))

from wsgiref.handlers import CGIHandler

from app import app


class PrefixCGIHandler(CGIHandler):
    def setup_environ(self):
        super(PrefixCGIHandler, self).setup_environ()
        self.environ["SCRIPT_NAME"] = "/tools/blindcard"


if __name__ == "__main__":
    PrefixCGIHandler().run(app)
