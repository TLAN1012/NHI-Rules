/* 共擬會議與給付改善方案異動 */
(async function () {
  const $ = (sel) => document.querySelector(sel);

  async function loadJSON(name, fallback) {
    try {
      const resp = await fetch(`data/${name}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      if (fallback !== undefined) return fallback;
      throw e;
    }
  }

  const topicsData = await loadJSON("topics.json", null);
  const changesData = await loadJSON("topic_changes.json", { changes: [] });

  if (!topicsData) {
    $("#changeList").innerHTML =
      "<p>尚無資料。首次抓取完成後才會有內容；若以 file:// 開啟，請改用本機伺服器：python3 -m http.server</p>";
    return;
  }

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toROC = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    return `${y - 1911}.${String(m).padStart(2, "0")}.${String(d).padStart(2, "0")}`;
  };
  const topicName = (key) => topicsData.topics.find((t) => t.key === key)?.name || key;

  /* ---------- 分頁切換 ---------- */
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#panel-${btn.dataset.tab}`).classList.add("active");
    });
  });

  /* ---------- 變動紀錄 ---------- */
  const TYPE_LABEL = { added: "新增項目", files_changed: "附件更新", removed: "已下架" };

  const topicSelect = $("#changeTopic");
  topicsData.topics.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t.key;
    opt.textContent = t.name;
    topicSelect.appendChild(opt);
  });

  function changeDetail(c) {
    if (c.type === "added") {
      const files = c.detail?.files || [];
      return files.length ? `<li>附件：${files.map(esc).join("、")}</li>` : "";
    }
    if (c.type === "files_changed") {
      const added = (c.detail?.added || []).map((f) => `<li>新增檔案：${esc(f)}</li>`).join("");
      const removed = (c.detail?.removed || []).map((f) => `<li>移除檔案：${esc(f)}</li>`).join("");
      return added + removed;
    }
    return "";
  }

  function renderChanges() {
    const topic = topicSelect.value;
    const type = $("#changeType").value;
    const rows = changesData.changes.filter(
      (c) => (!topic || c.topic === topic) && (!type || c.type === type)
    );
    $("#changeCount").textContent = rows.length ? `共 ${rows.length} 筆變動` : "";

    if (!rows.length) {
      $("#changeList").innerHTML =
        "<p class=\"hint\">目前沒有符合條件的變動紀錄。首次抓取只建立基準線，之後偵測到的異動才會出現在這裡。</p>";
      return;
    }

    // 依偵測日期分組，同一天抓到的變動放在一起
    const groups = new Map();
    for (const c of rows) {
      const day = (c.detected_at || "").slice(0, 10);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(c);
    }

    $("#changeList").innerHTML = [...groups.entries()]
      .map(([day, list]) => {
        const items = list
          .map((c) => {
            const detail = changeDetail(c);
            return `<li>
              <span class="badge">${esc(TYPE_LABEL[c.type] || c.type)}</span>
              <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title || c.item_key)}</a>
              <span class="count">${esc(topicName(c.topic))}${c.date ? `　會議／發布日 ${esc(toROC(c.date))}` : ""}</span>
              ${detail ? `<ul>${detail}</ul>` : ""}
            </li>`;
          })
          .join("");
        return `<h3>${esc(day)} <span class="count">${list.length} 筆</span></h3><ul>${items}</ul>`;
      })
      .join("");
  }

  topicSelect.addEventListener("change", renderChanges);
  $("#changeType").addEventListener("change", renderChanges);
  renderChanges();

  /* ---------- 各專區項目清單 ---------- */
  function fileLinks(files) {
    return (files || [])
      .map(
        (f) =>
          `<a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(f.title)}">${esc(f.file_type)}</a><span class="file-size">${esc(f.size)}</span>`
      )
      .join("");
  }

  function renderTopic(key) {
    const topic = topicsData.topics.find((t) => t.key === key);
    const listEl = $(`#${key}List`);
    if (!topic) {
      listEl.innerHTML = "<li>尚無資料</li>";
      return;
    }
    const q = $(`#${key}Search`).value.trim().toLowerCase();
    const items = topic.items.filter((i) => !q || (i.title || "").toLowerCase().includes(q));
    $(`#${key}Count`).textContent = `共 ${items.length} 筆${q ? `（全部 ${topic.items.length} 筆）` : ""}`;
    listEl.innerHTML = items
      .map(
        (i) => `<li>
          <span class="file-name">
            <a href="${esc(i.url)}" target="_blank" rel="noopener">${esc(i.title || i.key)}</a>
            ${i.date ? `<span class="count">　${esc(toROC(i.date))}</span>` : ""}
          </span>
          <span class="file-links">${fileLinks(i.files)}</span>
        </li>`
      )
      .join("");
  }

  for (const topic of topicsData.topics) {
    const hint = $(`#${topic.key}Hint`);
    if (hint) {
      hint.textContent = topic.stale
        ? `注意：最近一次抓取不完整，本清單可能未含最新項目（資料時間 ${(topicsData.generated_at || "").slice(0, 10)}）。`
        : `資料來源：${topic.name}專區，共 ${topic.items.length} 筆。`;
    }
    const search = $(`#${topic.key}Search`);
    if (search) search.addEventListener("input", () => renderTopic(topic.key));
    renderTopic(topic.key);
  }

  if (topicsData.generated_at) {
    $("#metaInfo").textContent = `資料更新時間：${topicsData.generated_at.replace("T", " ").replace("+00:00", " UTC")}`;
  }
})();
