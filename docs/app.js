/* 健保藥品給付規定查詢站 */
(async function () {
  const $ = (sel) => document.querySelector(sel);

  async function loadJSON(name) {
    const resp = await fetch(`data/${name}`);
    if (!resp.ok) throw new Error(`載入 ${name} 失敗：HTTP ${resp.status}`);
    return resp.json();
  }

  let announcements = [], chapters = { items: [] }, history = { items: [] }, meta = {}, fulldoc = {}, rulesData = { chapters: [], rules: [] };
  try {
    [announcements, chapters, history, meta] = await Promise.all([
      loadJSON("announcements.json"),
      loadJSON("chapters.json"),
      loadJSON("history.json"),
      loadJSON("meta.json"),
    ]);
    fulldoc = await loadJSON("fulldoc.json").catch(() => ({}));
    rulesData = await loadJSON("rules.json").catch(() => ({ chapters: [], rules: [] }));
  } catch (e) {
    $("#annList").innerHTML = `<li>資料載入失敗（${e.message}）。若以 file:// 開啟，請改用本機伺服器：python3 -m http.server</li>`;
    return;
  }

  /* ---------- 工具 ---------- */
  const toROC = (iso) => {
    if (!iso) return "—";
    const [y, m, d] = iso.split("-").map(Number);
    return `${y - 1911}.${String(m).padStart(2, "0")}.${String(d).padStart(2, "0")}`;
  };
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---------- 分頁切換 ---------- */
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#panel-${btn.dataset.tab}`).classList.add("active");
    });
  });

  /* ---------- 給付規定全文查詢 ---------- */
  const ruleChapterSel = $("#ruleChapter");
  rulesData.chapters.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.chapter;
    opt.textContent = c.chapter === 0 ? "通則" : `第${c.chapter}節 ${c.name}`;
    ruleChapterSel.appendChild(opt);
  });

  const highlight = (s, q) => {
    const escaped = esc(s);
    if (!q) return escaped;
    const safe = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return escaped.replace(new RegExp(`(${esc(safe)})`, "gi"), "<mark>$1</mark>");
  };

  function renderRules() {
    const q = $("#ruleSearch").value.trim();
    const ch = ruleChapterSel.value;
    const lq = q.toLowerCase();
    const filtered = rulesData.rules.filter((r) => {
      if (ch !== "" && String(r.chapter) !== ch) return false;
      if (lq && !(r.id + r.heading + r.text).toLowerCase().includes(lq)) return false;
      return true;
    });
    $("#ruleCount").textContent =
      `共 ${filtered.length} 條（資料庫共 ${rulesData.rules.length} 條給付規定）` +
      (q ? "" : "｜輸入關鍵字開始搜尋，或選擇章節瀏覽");
    const openAttr = q && filtered.length <= 10 ? " open" : "";
    $("#ruleList").innerHTML = filtered
      .slice(0, 100)
      .map(
        (r) => `<details${openAttr}>
          <summary><span class="rule-id">${esc(r.id)}</span>${highlight(r.heading || "（無標題）", q)}
            <span class="rule-chapter">${r.chapter === 0 ? "通則" : `第${r.chapter}節 ${esc(r.chapter_name)}`}</span>
          </summary>
          <div class="rule-text">${highlight(r.text, q)}</div>
        </details>`
      )
      .join("");
    if (filtered.length > 100)
      $("#ruleList").insertAdjacentHTML("beforeend", "<p class='hint'>…僅顯示前 100 條，請縮小搜尋範圍。</p>");
  }
  $("#ruleSearch").addEventListener("input", renderRules);
  ruleChapterSel.addEventListener("input", renderRules);
  renderRules();

  /* ---------- 最新公告 ---------- */
  const yearSel = $("#yearFilter");
  [...new Set(announcements.map((a) => (a.issued_date || "").slice(0, 4)).filter(Boolean))]
    .sort()
    .reverse()
    .forEach((y) => {
      const opt = document.createElement("option");
      opt.value = y;
      opt.textContent = `${y}（民國 ${y - 1911} 年）`;
      yearSel.appendChild(opt);
    });

  function renderAnnouncements() {
    const q = $("#search").value.trim().toLowerCase();
    const drugOnly = $("#drugOnly").checked;
    const year = yearSel.value;
    const filtered = announcements.filter((a) => {
      if (drugOnly && !a.is_drug_rule) return false;
      if (year && (a.issued_date || "").slice(0, 4) !== year) return false;
      if (q && !(a.title + a.doc_no).toLowerCase().includes(q)) return false;
      return true;
    });
    $("#annCount").textContent = `共 ${filtered.length} 筆（資料庫共 ${announcements.length} 筆公告）`;
    $("#annList").innerHTML = filtered
      .slice(0, 300)
      .map(
        (a) => `<li>
          <span class="ann-date" title="${esc(a.issued_date || "")}">${toROC(a.issued_date)}</span>
          <a class="ann-title" href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
          ${a.is_drug_rule ? '<span class="badge">藥品給付</span>' : ""}
          <span class="ann-doc">${esc(a.doc_no)}</span>
        </li>`
      )
      .join("");
    if (filtered.length > 300)
      $("#annList").insertAdjacentHTML("beforeend", `<li>…僅顯示前 300 筆，請縮小搜尋範圍。</li>`);
  }
  ["#search", "#drugOnly", "#yearFilter"].forEach((sel) =>
    $(sel).addEventListener("input", renderAnnouncements)
  );
  renderAnnouncements();

  /* ---------- 變化時間軸 ---------- */
  function renderTimeline() {
    const byMonth = new Map();
    announcements
      .filter((a) => a.is_drug_rule && a.issued_date)
      .forEach((a) => {
        const key = a.issued_date.slice(0, 7);
        if (!byMonth.has(key)) byMonth.set(key, []);
        byMonth.get(key).push(a);
      });
    const months = [...byMonth.keys()].sort().reverse();
    $("#timeline").innerHTML = months
      .map((m) => {
        const [y, mo] = m.split("-");
        const items = byMonth.get(m);
        return `<h3>民國 ${y - 1911} 年 ${Number(mo)} 月 <span class="count">（${items.length} 件）</span></h3>
          <ul>${items
            .map(
              (a) =>
                `<li><span class="ann-date">${toROC(a.issued_date)}</span><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a></li>`
            )
            .join("")}</ul>`;
      })
      .join("");
  }
  renderTimeline();

  /* ---------- 分章節 ---------- */
  function fileLinks(files) {
    return files
      .map(
        (f) =>
          `<a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.title)}">${esc(f.file_type)}</a><span class="file-size">${esc(f.size)}</span>`
      )
      .join("");
  }
  function renderChapters() {
    const q = $("#chapterSearch").value.trim().toLowerCase();
    const items = chapters.items.filter((c) => !q || c.name.toLowerCase().includes(q));
    $("#chapterList").innerHTML = items
      .map(
        (c) => `<li><span class="file-name">${esc(c.name)}</span><span class="file-links">${fileLinks(c.files)}</span></li>`
      )
      .join("");
  }
  /* ---------- 整份帶走 ---------- */
  if (fulldoc.title && fulldoc.downloads?.length) {
    $("#fulldocCard").hidden = false;
    $("#fulldocTitle").textContent = fulldoc.title;
    const links = fulldoc.downloads.flatMap((d) => d.files.map(
      (f) => `<a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.title)}">${esc(f.file_type)}</a><span class="file-size">${esc(f.size)}</span>`
    ));
    links.push(`<a href="files/nhi-drug-rules-full-1150723.pdf" title="站內備份（115.7.23 更新完整版）">站內備份 PDF（115.7.23）</a>`);
    $("#fulldocLinks").innerHTML = links.join("");
  }

  const chSrc = (chapters.source || "").replace("wayback:", "");
  $("#chaptersMeta").textContent = chapters.source?.startsWith("wayback")
    ? `注意：章節清單取自 ${chSrc.slice(0, 4)}-${chSrc.slice(4, 6)} 的網頁存檔，最新版請以健保署官網為準。`
    : "";
  $("#chapterSearch").addEventListener("input", renderChapters);
  renderChapters();

  /* ---------- 歷史檔 ---------- */
  $("#historyList").innerHTML = history.items
    .map(
      (h) => `<li><span class="file-name">${esc(h.name)}</span><span class="file-links">${fileLinks(h.files)}</span></li>`
    )
    .join("");

  /* ---------- meta ---------- */
  if (meta.generated_at) {
    $("#metaInfo").textContent =
      `資料更新時間：${meta.generated_at.replace("T", " ").replace("+00:00", " UTC")}｜` +
      `公告 ${meta.announcement_count} 筆（藥品給付相關 ${meta.drug_rule_count} 筆）` +
      (meta.date_range ? `｜涵蓋 ${meta.date_range[0]} ～ ${meta.date_range[1]}` : "");
  }
})();
