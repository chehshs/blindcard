# BlindCardMaker

<p align="center">
  <img src="static/blindcard-maker.svg" alt="BlindCardMaker" width="280">
</p>

<p align="center">
  <strong>CSV または画面入力から、赤シートで消える解答欄付きの単語帳 PDF を作ります。</strong>
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-3776ab">
  <a href="https://yachi-note.net/tools/blindcard/"><img alt="Demo" src="https://img.shields.io/badge/demo-yachi--note.net-2f6f5e"></a>
</p>

## 概要

暗記用の穴埋めプリントを作る Web アプリです。左に問題、右に解答を色つきで印刷し、
赤シートをかぶせると解答だけが消えます。用紙は A6 / A5 / A4、印刷内容は
「問題と解答」「問題のみ」「白紙」から選べます。

- アプリ — https://yachi-note.net/tools/blindcard/
- 操作方法 — https://yachi-note.net/tools/blindcard/guide

読み込める CSV の形は [`examples/sample.csv`](examples/sample.csv) の通りです。

入力された問題・解答はサーバーに保存しません。PDF を返したら破棄します。

## 構造

```
app.py             HTTP 層。入力検証・レート制限・PDF の返却
pdf_generator.py   組版と PDF 生成（reportlab）。行の分割やページ割りもここ
templates/         画面（Vue 同梱）と使い方ページ
static/            ビルド済み CSS、ロゴ、favicon
fonts/             PDF に埋め込む日本語フォント
index.cgi          常駐プロセスを置けない環境向けの入口
tests/             Python 32 件 + JavaScript
```

処理の流れは単純で、状態を持ちません。

```
ブラウザ ──POST /api/preview-pdf──▶ 1 ページ目だけ生成 ──▶ PDF を iframe に表示
        └─POST /api/generate-pdf─▶ 全ページ生成 ─────────▶ PDF をダウンロード
```

## 技術的な工夫

- **プレビューが本物の PDF** — 画面用の模擬表示ではなく、実際に 1 ページ目を生成して返します。
  プレビューと出力がずれる余地がありません。
- **文字が枠から出ない** — 行に収まらない問題文はフォントを縮め、それでも入らなければ
  二分探索で末尾を省略します。1 ページの行数を 10 に増やしても罫線と重なりません。
- **フォントの埋め込み** — IPAex明朝をサブセット化して埋め込むため、閲覧・印刷する環境に
  日本語フォントが無くても崩れません（フォントを同梱しない構成では CID フォントに戻します）。
- **番号でページを分ける** — `1-1` `1-2` のようにハイフンを含む番号は前半をひとまとまりと見なし、
  変わり目で改ページします。連番や番号なしは詰めて配置します。
- **外部 CDN に依存しない** — Vue は同梱、CSS はビルド済みを配信します。オフラインでも崩れません。
- **文字コードの自動判定** — CSV は UTF-8（BOM 付きを含む）と Shift_JIS のどちらでも読めます。
  Excel から書き出したファイルがそのまま通ります。

公開 API には IP ごとのレート制限、リクエストサイズ・件数・ページ数の上限、
CSP を含むセキュリティヘッダーを設定しています。テストは push のたびに
GitHub Actions で実行しています（Python / JavaScript）。

## ライセンス

アプリは MIT（[LICENSE](LICENSE)）。PDF に埋め込む日本語フォント IPAex明朝 は
[IPA Font License Agreement v1.0](fonts/IPA_Font_License_Agreement_v1.0.txt) に従います。
