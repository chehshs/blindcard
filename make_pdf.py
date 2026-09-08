"""CLI: CSV から暗記カード PDF を生成する。"""

import os
import sys

import pandas as pd

from pdf_generator import generate_anki_pdf


def read_anki_csv(path: str) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    print("エラー: CSVの文字コードを判定できませんでした。UTF-8 または Shift_JIS で保存してください。")
    if last_error:
        print(last_error)
    sys.exit(1)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "CSV", "kanji_matched.csv")

    if not os.path.exists(csv_path):
        csv_dir = os.path.join(base_dir, "CSV")
        if os.path.exists(csv_dir):
            files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
            if files:
                csv_path = os.path.join(csv_dir, files[0])

    if not os.path.exists(csv_path):
        print(f"エラー: CSVファイルが見つかりません -> {csv_path}")
        sys.exit(1)

    df = read_anki_csv(csv_path)
    has_note = len(df.columns) >= 4
    data = []
    for _, row in df.iterrows():
        note = ""
        if has_note and pd.notna(row.iloc[3]):
            note = str(row.iloc[3])
        data.append(
            {
                "num": "" if pd.isna(row.iloc[0]) else str(row.iloc[0]),
                "question": "" if pd.isna(row.iloc[1]) else str(row.iloc[1]),
                "answer": "" if pd.isna(row.iloc[2]) else str(row.iloc[2]),
                "note": note,
            }
        )

    output_dir = os.path.join(base_dir, "出力")
    os.makedirs(output_dir, exist_ok=True)
    output_pdf_path = os.path.join(output_dir, "anki_notebook_a6.pdf")

    pdf_bytes = generate_anki_pdf(
        data=data,
        paper_size="A6",
        rows_per_page=5,
        answer_color="#FFA500",
    )
    with open(output_pdf_path, "wb") as fh:
        fh.write(pdf_bytes)
    print(f"PDF作成完了: {output_pdf_path}")


if __name__ == "__main__":
    main()
