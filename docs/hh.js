/* 居家醫療照護整合計畫（健保署）＋ 居家失能個案家庭醫師照護方案（長照司）
 *
 * 兩案相關但不同：主管機關、財源、申報系統、給付標準均異，但自 115.06.30
 * 失能方案修正後，照管專員僅得就居整計畫收案且同一團隊照顧之個案派案。
 * 首頁分頁為「兩案對照」，逐項標明差異與銜接規定（scraper/dis_vs_hh.json）。
 *
 * 居整問答集（109.09.28 第五版）與現行計畫（115.03.18）扞格者，答覆已依現行
 * 條文校訂（校訂表：scraper/hh_qa_revisions.json），原文保留於題內可展開對照。
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

  async function loadJSON(name) {
    const resp = await fetch(`data/${name}`);
    if (!resp.ok) throw new Error(`載入 ${name} 失敗：HTTP ${resp.status}`);
    return resp.json();
  }

  let qa = { entries: [], staleness: {} }, plan = { sections: [], revisions: [] };
  let disPlan = { sections: [], attachments: [], form_revisions: [] };
  let disQa = { entries: [] }, cmp = { rows: [], links: [], notes: [], plans: {} };
  try {
    [plan, qa, disPlan, disQa, cmp] = await Promise.all([
      loadJSON("hh_plan.json"), loadJSON("hh_qa.json"),
      loadJSON("dis_plan.json"), loadJSON("dis_qa.json"), loadJSON("dis_vs_hh.json"),
    ]);
  } catch (e) {
    $("#cmpTable").innerHTML = `<tr><td>資料載入失敗（${esc(e.message)}）。若以 file:// 開啟，請改用本機伺服器。</td></tr>`;
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

  /* ============ 居整計畫全文 ============ */
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
      .slice().reverse()
      .map((r) => `<li>${esc(r.date_roc)}　${esc(r.doc_no)}　${esc(r.kind)}</li>`)
      .join("");
  }

  /* ============ 居整問答集（答覆已依現行計畫校訂） ============ */
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
      .slice().reverse()
      .map((r) => `<li>${esc(r.date_roc)}　${esc(r.doc_no)}　${esc(r.kind)}</li>`)
      .join("");
  }

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

  /* ============ 失能方案全文（含附件） ============ */
  const disAll = [...disPlan.sections, ...(disPlan.attachments || [])];
  $("#disMeta").textContent = disPlan.title
    ? `${disPlan.title}（${disPlan.agency}）　現行版本 ${disPlan.version}　${disPlan.doc_no}` +
      `｜期程：${disPlan.period}｜共 ${disPlan.sections.length} 章、附件 ${(disPlan.attachments || []).length} 份`
    : "";
  const disSel = $("#disSection");
  disAll.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = String(s.no);
    opt.textContent = s.no >= 100 ? s.title : `${s.id}、${s.title}`;
    disSel.appendChild(opt);
  });

  function renderDis() {
    const q = $("#disSearch").value.trim();
    const lq = q.toLowerCase();
    const only = disSel.value;
    const filtered = disAll.filter((s) => {
      if (only && String(s.no) !== only) return false;
      return !lq || (s.id + s.title + s.text).toLowerCase().includes(lq);
    });
    const openAttr = q || only ? " open" : "";
    $("#disList").innerHTML =
      filtered
        .map(
          (s) => `<details id="dsec-${s.no}"${openAttr}>
          <summary><span class="rule-id">${esc(s.id)}</span>${highlight(s.title, q)}</summary>
          <div class="rule-text">${highlight(s.text, q)}</div>
        </details>`
        )
        .join("") || "<p class='hint'>沒有符合的章節。</p>";
  }
  $("#disSearch").addEventListener("input", renderDis);
  disSel.addEventListener("input", renderDis);
  renderDis();

  if (disPlan.form_revisions?.length) {
    $("#disFormRevBox").hidden = false;
    $("#disFormRevList").innerHTML = disPlan.form_revisions
      .slice().reverse()
      .map((r) => `<li>${esc(r.date_roc)}　${esc(r.doc_no)}　${esc(r.kind)}</li>`)
      .join("");
  }

  /* ============ 失能方案問答 ============ */
  $("#disQaMeta").textContent = disQa.title
    ? `${disQa.title}（更新時間 ${disQa.version}），共 ${disQa.entries.length} 題`
    : "";
  function renderDisQa() {
    const q = $("#disQaSearch").value.trim();
    const lq = q.toLowerCase();
    const filtered = disQa.entries.filter(
      (e) => !lq || (e.question + e.answer + e.category).toLowerCase().includes(lq)
    );
    $("#disQaCount").textContent = `共 ${filtered.length} 題（資料庫共 ${disQa.entries.length} 題）`;
    // 題數少，預設全部展開
    $("#disQaList").innerHTML =
      filtered
        .map(
          (e) => `<details open>
          <summary><span class="rule-id">${e.no}</span><strong>Q：</strong>${highlight(e.question, q)}
            <span class="rule-chapter">${esc(e.category)}</span></summary>
          <div class="rule-text">${highlight(e.answer, q)}</div>
          ${(e.images || []).map((n) => `<img class="qa-img" src="img/${esc(n)}" alt="${esc(e.question)}附圖" loading="lazy">`).join("")}
        </details>`
        )
        .join("") || "<p class='hint'>沒有符合的問答。</p>";
  }
  $("#disQaSearch").addEventListener("input", renderDisQa);
  renderDisQa();

  /* ============ 兩案對照 ============ */
  const P = cmp.plans || {};
  $("#planCards").innerHTML = ["hh", "dis"]
    .filter((k) => P[k])
    .map(
      (k) => `<div class="plan-card" data-plan="${k}">
        <p class="plan-card-agency">${esc(P[k].agency)}</p>
        <h2>${esc(P[k].name)}</h2>
        <p class="plan-card-short">簡稱：${esc(P[k].short)}</p>
        <p class="plan-card-ver">${k === "hh"
          ? `現行版本 ${esc(plan.version || "")}`
          : `現行版本 ${esc(disPlan.version || "")}`}</p>
        <button class="plan-card-go" data-goto="${k === "hh" ? "plan" : "dis"}">看全文 →</button>
      </div>`
    )
    .join("");
  $("#cmpHint").textContent =
    "兩案為不同計畫，主管機關、財源、申報系統與給付標準均不同；" +
    "但自 115.06.30 失能方案修正後，照管專員僅得就居整計畫收案且同一團隊照顧之個案派案。" +
    "下表每列右側可點條號跳至該計畫全文覆核。";

  const secLink = (kind, no, label) =>
    no ? ` <a class="cmp-src" href="#" data-plan="${kind}" data-sec="${no}">${esc(label)}</a>` : "";
  const hhCn = (n) => (plan.sections.find((s) => s.no === n) || {}).id || n;
  const disCn = (n) => (disPlan.sections.find((s) => s.no === n) || {}).id || n;

  $("#cmpTable").innerHTML =
    `<thead><tr><th class="cmp-item">項目</th>
      <th data-plan="hh">居整計畫<span class="cmp-agency">健保署</span></th>
      <th data-plan="dis">失能方案<span class="cmp-agency">長照司</span></th></tr></thead><tbody>` +
    cmp.rows
      .map(
        (r) => `<tr>
        <th scope="row">${esc(r.item)}</th>
        <td>${esc(r.hh)}${secLink("hh", r.hh_sec, `第${hhCn(r.hh_sec)}點`)}</td>
        <td>${esc(r.dis)}${secLink("dis", r.dis_sec, `${disCn(r.dis_sec)}、`)}</td>
      </tr>`
      )
      .join("") +
    "</tbody>";

  $("#cmpLinks").innerHTML = (cmp.links || [])
    .map(
      (l) => `<div class="link-card">
        <p class="link-title">${esc(l.title)}</p>
        <p class="link-text">${esc(l.text)}</p>
        <p class="link-src">${l.hh_sec ? secLink("hh", l.hh_sec, `居整計畫第${hhCn(l.hh_sec)}點`) : ""}${
        l.dis_sec ? secLink("dis", l.dis_sec, `失能方案${disCn(l.dis_sec)}、`) : ""
      }</p>
      </div>`
    )
    .join("");

  $("#cmpNotes").innerHTML = (cmp.notes || [])
    .map((n) => `<div class="note-card"><p class="note-title">⚠ ${esc(n.title)}</p><p>${esc(n.text)}</p></div>`)
    .join("");

  /* 條號連結：切到對應計畫全文並展開該點 */
  document.addEventListener("click", (ev) => {
    const go = ev.target.closest("[data-goto]");
    if (go) {
      ev.preventDefault();
      activate(go.dataset.goto);
      history.replaceState(null, "", `#${go.dataset.goto}`);
      return;
    }
    const a = ev.target.closest("a[data-sec]");
    if (!a) return;
    ev.preventDefault();
    const isDis = a.dataset.plan === "dis";
    const sel = isDis ? disSel : secSel;
    sel.value = a.dataset.sec;
    (isDis ? renderDis : renderPlan)();
    activate(isDis ? "dis" : "plan");
    document.getElementById(`${isDis ? "dsec" : "sec"}-${a.dataset.sec}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  /* ============ 檔案下載 ============ */
  const files = [
    plan.file && { name: `${plan.title}（${plan.version} 公告修訂版）`, href: `files/${plan.file}`, tag: "hh" },
    qa.file && { name: `${qa.title}（${qa.version}）`, href: `files/${qa.file}`, tag: "hh" },
    disPlan.file && { name: `${disPlan.title}（${disPlan.version} 公告修正版）`, href: `files/${disPlan.file}`, tag: "dis" },
    disQa.file && { name: `${disQa.title}（更新時間 ${disQa.version}）`, href: `files/${disQa.file}`, tag: "dis" },
  ].filter(Boolean);
  $("#hhFiles").innerHTML = files
    .map(
      (f) =>
        `<li><span class="file-name"><span class="plan-dot" data-plan="${f.tag}"></span>${esc(f.name)}</span>` +
        `<span class="file-links"><a href="${esc(f.href)}" target="_blank" rel="noopener">pdf</a></span></li>`
    )
    .join("");

  $("#hhFooterMeta").textContent = plan.generated_at
    ? `資料建置時間：${plan.generated_at.replace("T", " ").replace("+00:00", " UTC")}`
    : "";
})();
