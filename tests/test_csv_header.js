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

function firstPageRows(rows, perPage) {
  const n = Number(perPage) || 1;
  if (!rows.length) return [];
  const firstKey = String(rows[0].num || "").includes("-")
    ? String(rows[0].num).trim().split("-", 2)[0].trim()
    : "";
  const group = [];
  for (let i = 0; i < rows.length; i++) {
    const raw = String(rows[i].num || "").trim();
    const key = raw.includes("-") ? raw.split("-", 2)[0].trim() : "";
    if (key !== firstKey) break;
    group.push(rows[i]);
  }
  return group.slice(0, n);
}

const preview = firstPageRows(
  [{ num: "1-1" }, { num: "1-2" }, { num: "2-1" }],
  5
);
if (preview.length !== 2 || preview[1].num !== "1-2") {
  console.error("FAIL firstPageRows", preview);
  process.exit(1);
}
console.log("ok firstPageRows");

