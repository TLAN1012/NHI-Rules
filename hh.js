/* 居家醫療照護整合計畫查詢
 *
 * 問答集為 109.09.28 第五版，計畫本文已更新至 115.03.18，其間計畫多次修訂。
 * 與現行計畫扞格者，答覆已依現行條文校訂（校訂表：scraper/hh_qa_revisions.json）：
 *   - 條號位移：逕行換算為現行條號
 *   - 實質規定變更：改寫答覆並註明理由與依據條號
 *   - 前提已變更：保留原答覆，加註前提說明
 * 原始答覆一律保留，於各題內可展開對照，使用者得自行覆核每一處更動。
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
      `⚠ 問答集為 ${qa.version}，計畫本文現行版本為 ${st.plan_version} — 答覆已依現行計畫校訂`;
    const c = qa.revision_summary || {};
    $("#staleBody").textContent =
      `問答集定版後，計畫另經 ${st.later_revisions.length} 次公告修訂，條號亦曾更動。` +
      `本頁已逐題比對現行計畫：實質規定已變更 ${c.substantive || 0} 題、題目前提已變更 ${c.premise || 0} 題、` +
      `僅條號換算 ${c.renumber || 0} 題、現行另有增訂 ${c.supplement || 0} 題。` +
      `各題顯示的是校訂後答覆，原始答覆保留於題內可展開對照；仍請以計畫全文為最終依據。`;
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
  const revSel = $("#qaRevision");
  $("#qaMeta").textContent = qa.revision_note || "";

  const REV_LABEL = {
    substantive: "實質規定已變更",
    premise: "題目前提已變更",
    renumber: "條號已換算",
    supplement: "現行另有增訂",
  };

  // 校訂說明：更動理由、依據之現行條號、條號位移對照
  function revisionBlock(e) {
    const r = e.revision;
    if (!r) return "";
    const parts = [];
    if (r.explain) parts.push(`<p class="rev-why">${esc(r.explain)}</p>`);
    if (e.renumbered?.length) {
      parts.push(
        `<p class="rev-moved">條號換算：${e.renumbered
          .map((m) => `計畫第${esc(m.from)}點 → 現行第${esc(m.to)}點`)
          .join("；")}</p>`
      );
    }
    if (r.basis?.length) {
      parts.push(
        `<p class="rev-basis">依據現行計畫：${r.basis
          .map((b) => `<a href="#" data-sec="${b.no}">第${esc(b.cn)}點 ${esc(b.title)}</a>`)
          .join("、")}</p>`
      );
    }
    if (!parts.length) return "";
    return `<div class="rev-box" data-kind="${esc(r.type)}">
      <p class="rev-head">校訂說明（${esc(REV_LABEL[r.type] || r.type)}）</p>${parts.join("")}</div>`;
  }

  function renderQA() {
    const q = $("#qaSearch").value.trim();
    const lq = q.toLowerCase();
    const cat = catSel.value;
    const rev = revSel.value;
    const filtered = qa.entries.filter((e) => {
      if (cat && e.category !== cat) return false;
      const kind = e.revision?.type || "";
      if (rev === "changed" ? !kind : rev && kind !== rev) return false;
      if (lq && ![e.question, e.answer, e.revised_answer, e.category, e.note, e.unit, e.revision?.explain]
                  .join("").toLowerCase().includes(lq)) return false;
      return true;
    });
    $("#qaCount").textContent = `共 ${filtered.length} 題（資料庫共 ${qa.entries.length} 題）`;
    const openAttr = q && filtered.length <= 8 ? " open" : "";
    $("#qaList").innerHTML =
      filtered
        .map((e) => {
          const kind = e.revision?.type || "";
          const shown = e.revised_answer || e.answer;
          const changed = Boolean(e.revised_answer);
          return `<details${openAttr}>
          <summary><span class="rule-id">${e.no}</span><strong>Q：</strong>${highlight(e.question, q)}
            <span class="rule-chapter">${esc(e.category)}${e.unit ? `｜${esc(e.unit)}` : ""}</span>
            ${kind ? `<span class="rev-badge" data-kind="${esc(kind)}">${esc(REV_LABEL[kind])}</span>` : ""}
          </summary>
          ${changed ? `<p class="ans-head">答覆（已依 ${esc(st.plan_version || "現行計畫")} 計畫校訂）</p>` : ""}
          <div class="rule-text">${highlight(shown, q)}</div>
          ${revisionBlock(e)}
          ${changed
            ? `<details class="orig-box"><summary>原始答覆（${esc(qa.version)}）</summary>
                 <div class="rule-text">${highlight(e.answer, q)}</div></details>`
            : ""}
          ${e.note ? `<p class="qa-note">問答集修訂說明：${esc(e.note)}</p>` : ""}
        </details>`;
        })
        .join("") || "<p class='hint'>沒有符合的問答。</p>";
  }
  $("#qaSearch").addEventListener("input", renderQA);
  catSel.addEventListener("input", renderQA);
  revSel.addEventListener("input", renderQA);
  renderQA();

  // 依據條號連結：切到計畫全文並展開該點
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
