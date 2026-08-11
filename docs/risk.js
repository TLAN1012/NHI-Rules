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
    let ldlMet = false;
    if (!isNaN(ldl)) {
      ldlMet = ldl >= info.start;
      judge = `LDL-C ${ldl} mg/dL：` + (ldlMet ? `已達起始藥物治療標準（≧${info.start}）` : `未達起始藥物治療標準（<${info.start}）`);
      if (nonHdl !== null) judge += `；non-HDL-C ${nonHdl} mg/dL`;
    } else if (nonHdl !== null) {
      judge = `non-HDL-C ${nonHdl} mg/dL`;
    }
    $("#ldlJudge").textContent = judge;
    // 達起始藥物治療門檻＝符合給付條件，以綠色加粗標示
    $("#ldlJudge").classList.toggle("ldl-met", ldlMet);

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

  function resetAll() {
    document.querySelectorAll('#panel-ascvd input[type="checkbox"]').forEach((el) => { el.checked = false; });
    document.querySelectorAll('#panel-ascvd input[type="number"]').forEach((el) => { el.value = ""; });
    document.querySelectorAll("#panel-ascvd details").forEach((el) => { el.open = false; });
    render();
    const btn = $("#resetBtn");
    btn.textContent = "已清空";
    setTimeout(() => { btn.textContent = "🗑 清空所有選項"; }, 1500);
    $("#panel-ascvd").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ==================== MASLD／FIB-4 ==================== */

  const ALCOHOL = {
    none: { label: "MASLD（代謝功能障礙相關脂肪肝病）", note: "無或極少飲酒" },
    mod: { label: "MetALD（MASLD 併中等量飲酒）", note: "中等量飲酒" },
    high: { label: "ALD（酒精相關肝病為主）", note: "高量飲酒" },
  };

  function renderMasld() {
    const steatosis = $("#steatosis").checked;
    const cmrf = $$(".cmrf:checked").map(named);
    const alcoholEl = document.querySelector('input[name="alcohol"]:checked');
    const alcohol = alcoholEl ? alcoholEl.value : "none";

    // MASLD 分類
    let cls, clsLevel;
    if (!steatosis) {
      cls = "尚未確認脂肪變性";
      clsLevel = "none";
    } else if (!cmrf.length) {
      cls = alcohol === "high" ? "ALD（酒精相關肝病）" : "脂肪肝，但無代謝風險因子（非 MASLD）";
      clsLevel = "none";
    } else if (alcohol === "high") {
      cls = "ALD（酒精相關肝病為主）";
      clsLevel = "warn";
    } else if (alcohol === "mod") {
      cls = "MetALD（MASLD 併中等量飲酒）";
      clsLevel = "warn";
    } else {
      cls = "MASLD";
      clsLevel = "met";
    }
    $("#masldClass").textContent = cls;
    $("#masldClass").dataset.level = clsLevel;

    $("#masldCriteria").textContent = steatosis
      ? (cmrf.length ? `✓ 脂肪變性證據 ＋ ${cmrf.length} 項心臟代謝風險因子（${ALCOHOL[alcohol].note}）` : "✓ 脂肪變性證據，但未勾選任何心臟代謝風險因子")
      : "尚未勾選脂肪變性證據（MASLD 診斷之必要條件）";
    $("#cmrfList").textContent = cmrf.length ? `${cmrf.length} 項：${cmrf.join("；")}` : "0 項";

    // FIB-4 =（年齡 × AST）÷（血小板 × √ALT）
    const age = parseFloat($("#fAge").value);
    const ast = parseFloat($("#fAst").value);
    const alt = parseFloat($("#fAlt").value);
    const plt = parseFloat($("#fPlt").value);
    const ready = [age, ast, alt, plt].every((v) => !isNaN(v) && v > 0);
    let fib = null, stdText = "請填入年齡與檢驗值", advice = "—";

    if (ready) {
      fib = (age * ast) / (plt * Math.sqrt(alt));
      const f = fib.toFixed(2);
      $("#fibValue").textContent = f;
      const stdLow = fib < 1.3, stdHigh = fib > 2.67;
      $("#fibValue").dataset.level = stdLow ? "met" : stdHigh ? "high" : "warn";
      stdText = stdLow
        ? `${f}：低風險（<1.3）——進階纖維化可能性低`
        : stdHigh
        ? `${f}：高風險（>2.67）——進階纖維化（F3–F4）可能`
        : `${f}：不確定區間（1.3–2.67）——需進一步分層`;

      // 高齡調整（≧65 歲，低風險上限改用 2.0）
      if (age >= 65) {
        $("#fibAgedLabel").hidden = false;
        $("#fibAged").hidden = false;
        const agedLow = fib < 2.0;
        $("#fibAged").textContent = agedLow
          ? `${f}：低風險（<2.0，已套用高齡調整）`
          : fib > 2.67
          ? `${f}：高風險（>2.67）`
          : `${f}：不確定區間（2.0–2.67，已套用高齡調整）`;
        $("#fibAged").classList.toggle("ldl-met", agedLow);
      } else {
        $("#fibAgedLabel").hidden = true;
        $("#fibAged").hidden = true;
      }

      advice = stdLow
        ? "定期追蹤，並持續處置代謝風險因子（體重、血糖、血壓、血脂）。"
        : stdHigh
        ? "建議轉介肝膽腸胃專科，並考慮彈性造影（FibroScan／MRE）或肝切片確認纖維化分期。"
        : "建議以彈性造影（FibroScan LSM）、ELF 或其他二線檢查進一步分層。";
      if (age < 35) advice += "（註：FIB-4 於 35 歲以下族群準確度較低，判讀請併臨床評估。）";
    } else {
      $("#fibValue").textContent = "—";
      $("#fibValue").dataset.level = "none";
      $("#fibAgedLabel").hidden = true;
      $("#fibAged").hidden = true;
    }
    $("#fibStd").textContent = stdText;
    $("#fibStd").classList.toggle("ldl-met", ready && fib < 1.3);
    $("#fibAdvice").textContent = advice;

    // 病歷用文字
    const today = new Date();
    const roc = `${today.getFullYear() - 1911}.${String(today.getMonth() + 1).padStart(2, "0")}.${String(today.getDate()).padStart(2, "0")}`;
    const lines = [`[脂肪肝評估 ${roc}] 分類：${cls}`];
    if (steatosis) lines.push("脂肪變性：影像／組織學證實");
    if (cmrf.length) lines.push(`心臟代謝風險因子（${cmrf.length}項）：${cmrf.join("、")}`);
    lines.push(`飲酒量：${ALCOHOL[alcohol].note}`);
    if (ready) {
      lines.push(`FIB-4：${fib.toFixed(2)}（年齡${age}／AST ${ast}／ALT ${alt}／PLT ${plt}）`);
      lines.push(`判讀：${stdText.replace(/^[\d.]+：/, "")}`);
      if (age >= 65) lines.push(`高齡調整判讀（低風險上限2.0）：${$("#fibAged").textContent.replace(/^[\d.]+：/, "")}`);
      lines.push(`建議：${advice}`);
    }
    lines.push("依 2023 MASLD 國際命名共識與 FIB-4 指數評估（臨床參考，非健保給付判定）");
    $("#masldCopyPreview").value = lines.join("\n");
  }

  async function copyMasld() {
    const btn = $("#masldCopyBtn");
    let ok = false;
    try {
      await navigator.clipboard.writeText($("#masldCopyPreview").value);
      ok = true;
    } catch (e) {
      const ta = $("#masldCopyPreview");
      ta.focus(); ta.select();
      ok = document.execCommand("copy");
      ta.setSelectionRange(0, 0);
      btn.focus();
    }
    btn.textContent = ok ? "✅ 已複製，可貼入病歷" : "⚠️ 複製失敗，請手動選取下方文字";
    setTimeout(() => { btn.textContent = "📋 複製評估結果（貼病歷）"; }, 2500);
  }

  function resetMasld() {
    document.querySelectorAll('#panel-masld input[type="checkbox"]').forEach((el) => { el.checked = false; });
    document.querySelectorAll('#panel-masld input[type="number"]').forEach((el) => { el.value = ""; });
    const first = document.querySelector('#panel-masld input[name="alcohol"][value="none"]');
    if (first) first.checked = true;
    renderMasld();
    const btn = $("#masldResetBtn");
    btn.textContent = "已清空";
    setTimeout(() => { btn.textContent = "🗑 清空所有選項"; }, 1500);
    $("#panel-masld").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ==================== 分頁切換與初始化 ==================== */

  function showTab(name) {
    const btn = document.querySelector(`.tab[data-tab="${name}"]`);
    if (!btn) return;
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + name).classList.add("active");
  }
  document.querySelectorAll(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      showTab(btn.dataset.tab);
      history.replaceState(null, "", "#" + btn.dataset.tab);
    })
  );

  document.querySelectorAll("#panel-ascvd input").forEach((el) => el.addEventListener("input", render));
  document.querySelectorAll("#panel-masld input").forEach((el) => el.addEventListener("input", renderMasld));
  $("#copyBtn").addEventListener("click", copyToClipboard);
  $("#resetBtn").addEventListener("click", resetAll);
  $("#masldCopyBtn").addEventListener("click", copyMasld);
  $("#masldResetBtn").addEventListener("click", resetMasld);

  render();
  renderMasld();
  if (location.hash) showTab(location.hash.slice(1));
})();
