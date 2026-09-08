function looksLikeHeader(cells) {
  const first = String(cells[0] || "").trim();
  const joined = cells.map((c) => String(c).trim().toLowerCase()).join(",");
  if (!/(^|,)(番号|問題|解答|備考|num|question|answer|note)(,|$)/.test(joined)) {
    return false;
  }
  if (!first) return true;
  if (/[0-9]/.test(first) && !/^(番号|num|id)$/i.test(first)) return false;
  return true;
}

const cases = [
  [["1-1", "漢字の書き取り", "練習"], false],
  [["1-1", "今日はキカイだ", "機会"], false],
  [["番号", "問題", "解答", "備考"], true],
  [["番号", "書き（カタカナ入り例文）", "漢字（対象漢字）"], true],
  [["1", "問題", "解答"], false],
  [["num", "question", "answer"], true],
];

let failed = 0;
for (const [cells, expected] of cases) {
  const got = looksLikeHeader(cells);
  if (got !== expected) {
    console.error("FAIL", cells, "expected", expected, "got", got);
    failed += 1;
  }
}

if (failed) {
  process.exit(1);
}
console.log("ok", cases.length, "header cases");
