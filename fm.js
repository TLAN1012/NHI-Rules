/* 家醫計畫查詢 */
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

  let qa = { entries: [] }, plan = { sections: [], revisions: [] };
  try {
    qa = await loadJSON("fm_qa.json");
    plan = await loadJSON("fm_plan.json");
  } catch (e) {
    $("#qaList").innerHTML = `<p>資料載入失敗（${esc(e.message)}）。若以 file:// 開啟，請改用本機伺服器。</p>`;
  }

  // 重排抽取文字：合併硬換行、保留條列結構
  const LIST_MARK = /^(\d{1,2}\.|\(\d{1,2}\)|（[一二三四五六七八九十]{1,3}）|\([一二三四五六七八九十]{1,3}\)|[一二三四五六七八九十]{1,3}、|[IVXⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]{1,4}\.|附表|備註)/;
  const reflow = (text) => {
    const out = [];
    for (const raw of String(text).split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      const prev = out[out.length - 1];
      if (prev === undefined || LIST_MARK.test(line) || /[。！？]$/.test(prev)) {
        out.push(line);
      } else {
        const sep = /[A-Za-z0-9)%,;]$/.test(prev) && /^[A-Za-z0-9(]/.test(line) ? " " : "";
        out[out.length - 1] = prev + sep + line;
      }
    }
    return out.join("\n");
  };
  qa.entries.forEach((e) => { e.answer = reflow(e.answer); });
  plan.sections.forEach((s) => { s.text = reflow(s.text); });

  /* 分頁切換 */
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#panel-${btn.dataset.tab}`).classList.add("active");
    });
  });

  /* 問答集 */
  const catSel = $("#qaCategory");
  [...new Set(qa.entries.map((e) => e.category))].forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    catSel.appendChild(opt);
  });
  $("#qaMeta").textContent = qa.title ? `${qa.title}（${qa.version || ""}）` : "";

  function renderQA() {
    const q = $("#qaSearch").value.trim();
    const lq = q.toLowerCase();
    const cat = catSel.value;
    const filtered = qa.entries.filter((e) => {
      if (cat && e.category !== cat) return false;
      if (lq && !(e.question + e.answer + e.category + e.note).toLowerCase().includes(lq)) return false;
      return true;
    });
    $("#qaCount").textContent = `共 ${filtered.length} 題（資料庫共 ${qa.entries.length} 題）`;
    const openAttr = q && filtered.length <= 8 ? " open" : "";
    $("#qaList").innerHTML = filtered
      .map(
        (e) => `<details${openAttr}>
          <summary><strong>Q：</strong>${highlight(e.question, q)}
            <span class="rule-chapter">${esc(e.category)}${e.note ? `｜${esc(e.note)}` : ""}</span>
          </summary>
          <div class="rule-text">${highlight(e.answer, q)}</div>
        </details>`
      )
      .join("") || "<p class='hint'>沒有符合的問答。</p>";
  }
  $("#qaSearch").addEventListener("input", renderQA);
  catSel.addEventListener("input", renderQA);
  renderQA();

  /* 計畫全文 */
  $("#planMeta").textContent = plan.title
    ? `${plan.title}（${plan.revisions.length ? plan.revisions[plan.revisions.length - 1].trim() : ""}）`
    : "";
  function renderPlan() {
    const q = $("#planSearch").value.trim();
    const lq = q.toLowerCase();
    const filtered = plan.sections.filter(
      (s) => !lq || (s.id + s.title + s.text).toLowerCase().includes(lq)
    );
    const openAttr = q ? " open" : "";
    $("#planList").innerHTML = filtered
      .map(
        (s) => `<details${openAttr}>
          <summary><span class="rule-id">${esc(s.id)}</span>${highlight(s.title, q)}</summary>
          <div class="rule-text">${highlight(s.text, q)}</div>
        </details>`
      )
      .join("") || "<p class='hint'>沒有符合的章節。</p>";
  }
  $("#planSearch").addEventListener("input", renderPlan);
  renderPlan();

  if (plan.revisions?.length) {
    $("#revBox").hidden = false;
    $("#revList").innerHTML = plan.revisions.map((r) => `<li>${esc(r.trim())}</li>`).join("");
  }

  /* 檔案下載 */
  const files = [
    qa.file && { name: `${qa.title || "問答集"}（${qa.version || ""}）`, href: `files/${qa.file}` },
    plan.file && { name: `${plan.title || "計畫本文"}（115.06.26 公告修正版）`, href: `files/${plan.file}` },
  ].filter(Boolean);
  $("#fmFiles").innerHTML = files
    .map(
      (f) => `<li><span class="file-name">${esc(f.name)}</span><span class="file-links"><a href="${esc(f.href)}" target="_blank" rel="noopener">pdf</a></span></li>`
    )
    .join("");

  $("#fmFooterMeta").textContent = qa.generated_at
    ? `資料建置時間：${qa.generated_at.replace("T", " ").replace("+00:00", " UTC")}`
    : "";
})();
