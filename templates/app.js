const { createApp, ref, computed, watch } = Vue;

const COLOR_PRESETS = [
  { name: "オレンジ", value: "#FFA500" },
  { name: "赤", value: "#EF4444" },
  { name: "ローズ", value: "#EC4899" },
  { name: "マゼンタ", value: "#A855F7" },
];

function uid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "r-" + Math.random().toString(36).slice(2, 10);
}

function emptyRow(num) {
  return { id: uid(), num: num || "", question: "", answer: "", note: "" };
}

function defaultRows() {
  return Array.from({ length: 5 }, (_, i) => emptyRow("1-" + (i + 1)));
}

function parseCsv(text) {
  const src = String(text || "").replace(/^\uFEFF/, "");
  const rows = [];
  let field = "";
  let row = [];
  let inQuotes = false;

  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    const next = src[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((cell) => String(cell).trim() !== ""));
}

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

function csvCell(value) {
  return '"' + String(value || "").replace(/"/g, '""') + '"';
}

function sectionKey(num) {
  const raw = String(num || "").trim();
  if (!raw.includes("-")) return "";
  return raw.split("-", 2)[0].trim();
}

function sectionLabel(num) {
  return sectionKey(num) || "1";
}

function countEstimatedPages(rows, perPage) {
  const n = Number(perPage) || 1;
  if (!rows.length) return 0;
  let pages = 0;
  let currentKey = null;
  let count = 0;
  rows.forEach((row) => {
    const key = sectionKey(row.num);
    if (currentKey === null || key !== currentKey) {
      if (count) pages += Math.ceil(count / n);
      currentKey = key;
      count = 1;
    } else {
      count += 1;
    }
  });
  if (count) pages += Math.ceil(count / n);
  return pages;
}

function decodeCsvBuffer(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (_) {
    const labels = ["shift_jis", "shift-jis", "windows-31j"];
    for (let i = 0; i < labels.length; i++) {
      try {
        return new TextDecoder(labels[i]).decode(bytes);
      } catch (err) {
        /* try next */
      }
    }
    return new TextDecoder("utf-8").decode(bytes);
  }
}

function nextNum(rows) {
  const last = rows[rows.length - 1];
  if (!last || !String(last.num || "").trim()) {
    return "1-" + (rows.length + 1);
  }
  const parts = String(last.num).trim().split("-");
  if (parts.length >= 2 && /^\d+$/.test(parts[parts.length - 1])) {
    const suffix = Number(parts.pop()) + 1;
    return parts.join("-") + "-" + suffix;
  }
  return "1-" + (rows.length + 1);
}

createApp({
  delimiters: ["[[", "]]"],
  setup() {
    const paperSize = ref("A6");
    const rowsPerPage = ref(5);
    const kanjiColor = ref("#FFA500");
    const notebookTitle = ref("");
    const numberStyle = ref("raw");
    const showCheckbox = ref(false);
    const rows = ref(defaultRows());
    const fileName = ref("");
    const dragOver = ref(false);
    const generating = ref(false);
    const showClearModal = ref(false);
    const fileInput = ref(null);
    const alertState = ref(null);
    let alertTimer = null;

    const filledRows = computed(() =>
      rows.value.filter((row) =>
        [row.num, row.question, row.answer, row.note].some((v) => String(v || "").trim())
      )
    );

    const contentRows = computed(() =>
      filledRows.value.filter((row) => String(row.question || "").trim() || String(row.answer || "").trim())
    );

    const estimatedPages = computed(() => countEstimatedPages(filledRows.value, rowsPerPage.value));

    const previewRows = computed(() => {
      const perPage = Number(rowsPerPage.value);
      const source = filledRows.value.slice(0, perPage);
      const padded = source.map((row) => ({ ...row }));
      while (padded.length < perPage) {
        padded.push(emptyRow(""));
      }
      return padded;
    });

    const previewSection = computed(() => sectionLabel((filledRows.value[0] || {}).num));

    const previewTitle = computed(() => {
      const heading = String(notebookTitle.value || "").trim() || "ANKI NOTE";
      return heading + " - NO." + previewSection.value;
    });

    const colorHex = computed(() => String(kanjiColor.value || "#FFA500").toUpperCase());

    function formatDisplayNum(row, index) {
      if (numberStyle.value === "dot") {
        return (index + 1) + ".";
      }
      return (row && row.num) || "";
    }

    function showAlert(message, type) {
      alertState.value = { message, type: type || "ok" };
      if (alertTimer) clearTimeout(alertTimer);
      alertTimer = setTimeout(() => {
        alertState.value = null;
      }, 4200);
    }

    function hideAlert() {
      if (alertTimer) clearTimeout(alertTimer);
      alertState.value = null;
    }

    function addRow() {
      rows.value.push(emptyRow(nextNum(rows.value)));
    }

    function removeRow(id) {
      rows.value = rows.value.filter((row) => row.id !== id);
      if (!rows.value.length) {
        rows.value = [emptyRow("1-1")];
      }
    }

    function resetRows() {
      rows.value = defaultRows();
      fileName.value = "";
      hideAlert();
      showClearModal.value = false;
    }

    function collectRows() {
      return filledRows.value.map((row) => ({
        num: String(row.num || "").trim(),
        question: String(row.question || "").trim(),
        answer: String(row.answer || "").trim(),
        note: String(row.note || "").trim(),
      }));
    }

    function loadCsvText(text, name) {
      const parsed = parseCsv(text);
      if (!parsed.length) {
        showAlert("CSVに読み込める行がありません。", "error");
        return;
      }

      let start = 0;
      if (looksLikeHeader(parsed[0])) start = 1;

      const imported = [];
      for (let i = start; i < parsed.length; i++) {
        const cells = parsed[i];
        const num = (cells[0] || "").trim();
        const question = (cells[1] || "").trim();
        const answer = (cells[2] || "").trim();
        const note = (cells[3] || "").trim();
        if (num || question || answer || note) {
          imported.push(emptyRow(num));
          imported[imported.length - 1].question = question;
          imported[imported.length - 1].answer = answer;
          imported[imported.length - 1].note = note;
        }
      }

      if (!imported.length) {
        showAlert("有効なデータ行が見つかりませんでした。", "error");
        return;
      }

      rows.value = imported;
      fileName.value = name || "";
      showAlert(imported.length + " 件のデータを読み込みました。", "ok");
    }

    function readCsvFile(file) {
      if (!file) return;
      if (!/\.csv$/i.test(file.name) && file.type !== "text/csv") {
        showAlert("CSVファイルを選択してください。", "error");
        return;
      }
      const reader = new FileReader();
      reader.onload = (ev) => loadCsvText(decodeCsvBuffer(ev.target.result || new Uint8Array()), file.name);
      reader.onerror = () => showAlert("ファイルの読み込みに失敗しました。", "error");
      reader.readAsArrayBuffer(file);
    }

    function openFilePicker() {
      if (fileInput.value) fileInput.value.click();
    }

    function onFileChange(event) {
      const file = event.target.files && event.target.files[0];
      readCsvFile(file);
      event.target.value = "";
    }

    function onDragOver(event) {
      event.preventDefault();
      dragOver.value = true;
    }

    function onDragLeave() {
      dragOver.value = false;
    }

    function onDrop(event) {
      event.preventDefault();
      dragOver.value = false;
      const files = event.dataTransfer && event.dataTransfer.files;
      readCsvFile(files && files[0]);
    }

    function downloadCsv() {
      const dataList = [["番号", "問題", "解答", "備考"]];
      collectRows().forEach((row) => {
        dataList.push([csvCell(row.num), csvCell(row.question), csvCell(row.answer), csvCell(row.note)]);
      });
      if (dataList.length <= 1) {
        showAlert("保存するデータがありません。", "error");
        return;
      }
      const csvContent = "\uFEFF" + dataList.map((e) => e.join(",")).join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "anki_data_" + new Date().toISOString().slice(0, 10) + ".csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      showAlert("CSVを保存しました。", "ok");
    }

    async function generatePdf() {
      hideAlert();
      const payloadRows = collectRows();
      if (!payloadRows.some((row) => row.question || row.answer)) {
        showAlert("問題または解答が入力された行が必要です。", "error");
        return;
      }
      if (payloadRows.length > 2000) {
        showAlert("一度に出力できるのは2000件までです（現在" + payloadRows.length + "件）。", "error");
        return;
      }

      const payload = {
        paperSize: paperSize.value,
        rowsPerPage: Number(rowsPerPage.value),
        color: kanjiColor.value,
        title: String(notebookTitle.value || "").trim(),
        showCheckbox: !!showCheckbox.value,
        numberStyle: numberStyle.value,
        data: payloadRows,
      };

      generating.value = true;
      try {
        const res = await fetch("/api/generate-pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          let message = "PDF生成に失敗しました。";
          try {
            const err = await res.json();
            if (err && err.error) message = err.error;
          } catch (_) {
            /* ignore */
          }
          throw new Error(message);
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "anki_notebook_" + payload.paperSize.toLowerCase() + ".pdf";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showAlert("PDFを発行しました。ダウンロードを確認してください。", "ok");
      } catch (err) {
        showAlert((err && err.message) || "PDF生成に失敗しました。", "error");
      } finally {
        generating.value = false;
      }
    }

    watch(kanjiColor, (value) => {
      if (value && !value.startsWith("#")) {
        kanjiColor.value = "#FFA500";
      }
    });

    return {
      COLOR_PRESETS,
      paperSize,
      rowsPerPage,
      kanjiColor,
      notebookTitle,
      numberStyle,
      showCheckbox,
      rows,
      fileName,
      dragOver,
      generating,
      showClearModal,
      fileInput,
      alertState,
      filledRows,
      contentRows,
      estimatedPages,
      previewRows,
      previewSection,
      previewTitle,
      colorHex,
      formatDisplayNum,
      addRow,
      removeRow,
      resetRows,
      openFilePicker,
      onFileChange,
      onDragOver,
      onDragLeave,
      onDrop,
      downloadCsv,
      generatePdf,
    };
  },
}).mount("#app");

window.__ANKI_MOUNTED = true;
