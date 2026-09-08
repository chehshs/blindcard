# BlindCardMaker

CSV または画面入力から、赤シートで消える解答欄付きの単語帳 PDF（A6 / A5 / A4）を作ります。

## 起動

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

ブラウザで http://127.0.0.1:5000 を開きます。macOS では `run_web.command` でも同じです。CSV だけから PDF を出す場合は `run.command`（`make_pdf.py`）を使います。

デバッグ用の Werkzeug 再読み込みは既定オフです。必要なときだけ:

```bash
ANKI_DEBUG=1 python3 app.py
```

## 画面の CSS を直したとき

HTML の Tailwind クラスを変えたら、ビルド済み CSS を作り直します。

```bash
npm run build:css
```

成果物は `static/app.css` です。`static/input.css` がソースです。画面は CDN に依存しません。

## フォント

PDF の日本語は `fonts/ipaexm.ttf`（IPAex明朝）を埋め込んでいます。ライセンスは `fonts/IPA_Font_License_Agreement_v1.0.txt` を見てください。ファイルが無いときは従来の CID フォントに戻します。

## 使い方

アプリ内の [/guide](http://127.0.0.1:5000/guide) に、CSV の書き方・改ページ規則・赤シートの注意があります。
