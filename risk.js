/* ASCVD 風險等級計算（全民健康保險降膽固醇藥物給付規定表一，115.9.1 生效） */
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];

  // 各風險等級之起始藥物治療門檻與目標值（mg/dL）
  const LEVELS = {
    extreme: { label: "極高風險", start: 55, target: "LDL-C<55mg/dL（non-HDL-C<85mg/dL）" },
    veryhigh: { label: "非常高風險", start: 70, target: "LDL-C<70mg/dL（non-HDL-C<100mg/dL）" },
    high: { label: "高風險", start: 100, target: "LDL-C<100mg/dL（non-HDL-C<130mg/dL）" },
    mid: { label: "中風險（≧2 項風險因子）", start: 115, target: "LDL-C<115mg/dL（non-HDL-C<145mg/dL）" },
    low: { label: "低風險（1 項風險因子）", start: 130, target: "LDL-C<130mg/dL（non-HDL-C<160mg/dL）" },
    zero: { label: "0 項心血管風險因子", start: 160, target: "LDL-C<160mg/dL" },
  };

  const named = (el) => el.dataset.name || el.parentElement.textContent.trim();

  function evaluate() {
    const met = { extreme: [], veryhigh: [], high: [], factors: [] };

    const cad = $("#cad").checked;
    const pad = $("#pad").checked;
    const carotid = $("#carotid").checked;
    const cadCombos = $$(".cad-combo:checked").map(named);

    // 極高風險：CAD 合併（特定臨床狀況、PAD 或頸動脈狹窄）；或 PAD 合併（CAD 或頸動脈狹窄）
    if (cad && (cadCombos.length || pad || carotid)) {
      const combos = [...cadCombos];
      if (pad) combos.push("周邊動脈疾病");
      if (carotid) combos.push("頸動脈狹窄");
      met.extreme.push("冠狀動脈疾病合併：" + combos.join("、"));
    }
    if (pad && (cad || carotid)) {
      const combos = [];
      if (cad) combos.push("冠狀動脈疾病");
      if (carotid) combos.push("頸動脈狹窄");
      met.extreme.push("周邊動脈疾病合併：" + combos.join("、"));
    }

    met.veryhigh = $$(".vh:checked").map(named);
    met.high = $$(".hr:checked").map(named);

    // 心血管風險因子（代謝症候群需 ≥3 項成立）
    met.factors = $$(".rf:checked").map(named);
    const metsItems = $$(".mets:checked").map(named);
    const metsOK = metsItems.length >= 3;
    $("#metsState").textContent = metsOK
      ? `代謝性症候群（已勾 ${metsItems.length} 項，成立）`
      : `代謝性症候群（勾選以下至少 3 項才成立${metsItems.length ? `，目前 ${metsItems.length} 項` : ""}）`;
    if (metsOK) met.factors.push(`代謝性症候群（${metsItems.join("、")}）`);

    let level, conditions;
    if (met.extreme.length) {
      level = "extreme"; conditions = met.extreme;
    } else if (met.veryhigh.length) {
      level = "veryhigh"; conditions = met.veryhigh;
    } else if (met.high.length) {
      level = "high"; conditions = met.high;
    } else if (met.factors.length >= 2) {
      level = "mid"; conditions = met.factors;
    } else if (met.factors.length === 1) {
      level = "low"; conditions = met.factors;
    } else {
      level = "zero"; conditions = [];
    }
    return { level, conditions, factors: met.factors };
  }

  function render() {
    const { level, conditions, factors } = evaluate();
    const info = LEVELS[level];
    $("#riskLevel").textContent = info.label;
    $("#riskLevel").dataset.level = level;
    $("#threshold").textContent = `LDL-C≧${info.start}mg/dL`;
    $("#target").textContent = info.target;

    const ldl = parseFloat($("#ldl").value);
    const tc = parseFloat($("#tc").value);
    const hdl = parseFloat($("#hdl").value);
    const nonHdl = !isNaN(tc) && !isNaN(hdl) ? tc - hdl : null;

    let judge = "未輸入";
    if (!isNaN(ldl)) {
      judge = `LDL-C ${ldl} mg/dL：` + (ldl >= info.start ? `已達起始藥物治療標準（≧${info.start}）` : `未達起始藥物治療標準（<${info.start}）`);
      if (nonHdl !== null) judge += `；non-HDL-C ${nonHdl} mg/dL`;
    } else if (nonHdl !== null) {
      judge = `non-HDL-C ${nonHdl} mg/dL`;
    }
    $("#ldlJudge").textContent = judge;

    $("#metList").textContent = conditions.length
      ? conditions.join("；")
      : (level === "zero" ? "未勾選任何條件（0 項風險因子）" : "—");

    // 病歷用文字
    const today = new Date();
    const roc = `${today.getFullYear() - 1911}.${String(today.getMonth() + 1).padStart(2, "0")}.${String(today.getDate()).padStart(2, "0")}`;
    const lines = [
      `[ASCVD風險評估 ${roc}] 風險等級：${info.label}`,
    ];
    if (conditions.length) lines.push(`符合條件：${conditions.join("；")}`);
    if (["extreme", "veryhigh", "high"].includes(level) && factors.length)
      lines.push(`心血管風險因子（${factors.length}項）：${factors.join("、")}`);
    if (!isNaN(ldl)) {
      lines.push(`LDL-C：${ldl} mg/dL${nonHdl !== null ? `；non-HDL-C：${nonHdl} mg/dL` : ""}（起始藥物治療門檻 LDL-C≧${info.start}；目標 ${info.target}）`);
    } else {
      lines.push(`起始藥物治療門檻 LDL-C≧${info.start} mg/dL；目標 ${info.target}`);
    }
    lines.push(`依全民健康保險降膽固醇藥物給付規定表一（115.9.1生效）評估`);
    $("#copyPreview").value = lines.join("\n");
  }

  async function copyToClipboard() {
    const text = $("#copyPreview").value;
    const btn = $("#copyBtn");
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (e) {
      const ta = $("#copyPreview");
      ta.focus();
      ta.select();
      ok = document.execCommand("copy");
      ta.setSelectionRange(0, 0);
      btn.focus();
    }
    btn.textContent = ok ? "✅ 已複製，可貼入病歷" : "⚠️ 複製失敗，請手動選取下方文字";
    setTimeout(() => { btn.textContent = "📋 複製風險值與符合條件（貼病歷）"; }, 2500);
  }

  document.querySelectorAll("input").forEach((el) => el.addEventListener("input", render));
  $("#copyBtn").addEventListener("click", copyToClipboard);
  render();
})();
