/* 居家醫療照護整合計畫查詢
 *
 * 問答集為 109.09.28 第五版，計畫本文已更新至 115.03.18，其間計畫多次修訂，
 * 部分問答可能已不符現行規定。本頁不代為判斷問答對錯，只把對照資訊攤開：
 *   1. 問答集定版後的計畫修訂公告一覽
 *   2. 每題引用的「計畫第X點」，並列出現行計畫該點的標題供比對
 */
(async function () {
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const highlight = (s, q) => {
    const escaped = esc(s);
    if (!q) return escaped;
    const safe = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return escaped.replace(new RegExp(`(${esc(safe)})`, "gi"), "<mark>$1</mark>");
  };
  const rocOf = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    return m ? `${+m[1] - 1911}.${m[2]}.${m[3]}` : iso || "";
  };

  async function loadJSON(name) {
    const resp = await fetch(`data/${name}`);
    if (!resp.ok) throw new Error(`載入 ${name} 失敗：HTTP ${resp.status}`);
    return resp.json();
  }

  let qa = { entries: [], staleness: {} }, plan = { sections: [], revisions: [] };
  try {
    plan = await loadJSON("hh_plan.json");
    qa = await loadJSON("hh_qa.json");
  } catch (e) {
    $("#planList").innerHTML = `<p>資料載入失敗（${esc(e.message)}）。若以 file:// 開啟，請改用本機伺服器。</p>`;
  }

  /* 分頁切換（含 hash 直達，供書籤與分享連結使用） */
  function activate(name) {
    const btn = document.querySelector(`.tab[data-tab="${name}"]`);
    if (!btn) return;
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#panel-${name}`).classList.add("active");
  }
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      activate(btn.dataset.tab);
      history.replaceState(null, "", `#${btn.dataset.tab}`);
    });
  });
  const fromHash = () => activate(location.hash.replace("#", ""));
  window.addEventListener("hashchange", fromHash);
  if (location.hash) fromHash();

  /* 計畫全文 */
  $("#planMeta").textContent = plan.title
    ? `${plan.title}（現行版本 ${plan.version}　${plan.revisions?.length ? plan.revisions[plan.revisions.length - 1].doc_no : ""}），共 ${plan.sections.length} 點`
    : "";
  const secSel = $("#planSection");
  plan.sections.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = String(s.no);
    opt.textContent = `${s.id}、${s.title}`;
    secSel.appendChild(opt);
  });

  function renderPlan() {
    const q = $("#planSearch").value.trim();
    const lq = q.toLowerCase();
    const only = secSel.value;
    const filtered = plan.sections.filter((s) => {
      if (only && String(s.no) !== only) return false;
      return !lq || (s.id + s.title + s.text).toLowerCase().includes(lq);
    });
    const openAttr = q || only ? " open" : "";
    $("#planList").innerHTML =
      filtered
        .map(
          (s) => `<details id="sec-${s.no}"${openAttr}>
          <summary><span class="rule-id">${esc(s.id)}</span>${highlight(s.title, q)}</summary>
          <div class="rule-text">${highlight(s.text, q)}</div>
        </details>`
        )
        .join("") || "<p class='hint'>沒有符合的條號。</p>";
  }
  $("#planSearch").addEventListener("input", renderPlan);
  secSel.addEventListener("input", renderPlan);
  renderPlan();

  if (plan.revisions?.length) {
    $("#revBox").hidden = false;
    $("#revList").innerHTML = plan.revisions
      .slice()
      .reverse()
      .map((r) => `<li>${esc(r.date_roc)}　${esc(r.doc_no)}　${esc(r.kind)}</li>`)
      .join("");
  }

  /* 版本落差提示 */
  const st = qa.staleness || {};
  if (st.later_revisions?.length) {
    $("#staleBanner").hidden = false;
    $("#staleHead").textContent =
      `⚠ 問答集版本落後計畫本文：問答集為 ${qa.version}，計畫本文現行版本為 ${st.plan_version}`;
    $("#staleBody").textContent =
      `問答集定版後，計畫另經 ${st.later_revisions.length} 次公告修訂，條號亦曾更動。` +
      `以下問答未必仍符合現行規定，請以「計畫全文」分頁之現行條文為準。` +
      `引用計畫條號的題目下方會列出該條號在現行計畫的標題，供直接比對。`;
    $("#staleRevList").innerHTML = st.later_revisions
      .slice()
      .reverse()
      .map((r) => `<li>${esc(r.date_roc)}　${esc(r.doc_no)}　${esc(r.kind)}</li>`)
      .join("");
  }

  /* 問答集 */
  const catSel = $("#qaCategory");
  [...new Set(qa.entries.map((e) => e.category).filter(Boolean))].forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    catSel.appendChild(opt);
  });
  $("#qaMeta").textContent = qa.title
    ? `${qa.title}（${qa.version}），共 ${qa.entries.length} 題；「修訂說明」為問答集自身歷次改版之註記。`
    : "";

  function citeBlock(e) {
    if (!e.cite_map?.length) return "";
    const rows = e.cite_map
      .map(
        (c) =>
          `<li>本題引用「計畫第${esc(c.cn)}點」　→　現行計畫第${esc(c.cn)}點為
           <a href="#plan" data-sec="${c.no}">${esc(c.current_title)}</a></li>`
      )
      .join("");
    return `<div class="cite-map"><p class="cite-head">條號對照（問答集定版於 ${rocOf(st.qa_date)}，其後計畫已改版）</p><ul>${rows}</ul></div>`;
  }

  function renderQA() {
    const q = $("#qaSearch").value.trim();
    const lq = q.toLowerCase();
    const cat = catSel.value;
    const citeOnly = $("#citeOnly").checked;
    const filtered = qa.entries.filter((e) => {
      if (cat && e.category !== cat) return false;
      if (citeOnly && !e.cite_map?.length) return false;
      if (lq && !(e.question + e.answer + e.category + e.note + e.unit).toLowerCase().includes(lq)) return false;
      return true;
    });
    $("#qaCount").textContent = `共 ${filtered.length} 題（資料庫共 ${qa.entries.length} 題）`;
    const openAttr = q && filtered.length <= 8 ? " open" : "";
    $("#qaList").innerHTML =
      filtered
        .map(
          (e) => `<details${openAttr}>
          <summary><span class="rule-id">${e.no}</span><strong>Q：</strong>${highlight(e.question, q)}
            <span class="rule-chapter">${esc(e.category)}${e.unit ? `｜${esc(e.unit)}` : ""}${
            e.cite_map?.length ? "｜引用計畫條號" : ""
          }</span>
          </summary>
          <div class="rule-text">${highlight(e.answer, q)}</div>
          ${citeBlock(e)}
          ${e.note ? `<p class="qa-note">問答集修訂說明：${esc(e.note)}</p>` : ""}
        </details>`
        )
        .join("") || "<p class='hint'>沒有符合的問答。</p>";
  }
  $("#qaSearch").addEventListener("input", renderQA);
  catSel.addEventListener("input", renderQA);
  $("#citeOnly").addEventListener("input", renderQA);
  renderQA();

  // 條號對照連結：切到計畫全文並展開該點
  $("#qaList").addEventListener("click", (ev) => {
    const a = ev.target.closest("a[data-sec]");
    if (!a) return;
    ev.preventDefault();
    secSel.value = a.dataset.sec;
    renderPlan();
    activate("plan");
    $(`#sec-${a.dataset.sec}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  /* 檔案下載 */
  const files = [
    plan.file && { name: `${plan.title}（${plan.version} 公告修訂版）`, href: `files/${plan.file}` },
    qa.file && { name: `${qa.title}（${qa.version}）`, href: `files/${qa.file}` },
  ].filter(Boolean);
  $("#hhFiles").innerHTML = files
    .map(
      (f) =>
        `<li><span class="file-name">${esc(f.name)}</span><span class="file-links"><a href="${esc(
          f.href
        )}" target="_blank" rel="noopener">pdf</a></span></li>`
    )
    .join("");

  $("#hhFooterMeta").textContent = plan.generated_at
    ? `資料建置時間：${plan.generated_at.replace("T", " ").replace("+00:00", " UTC")}`
    : "";
})();
