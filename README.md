# 健保政策查詢站（NHI-Rules）

台灣全民健保各項政策公告的整理與查詢站（公告查詢性質，不涉及治療建議）。目前收錄：

1. **藥品給付規定**（`drug.html`）：逐條給付規定全文查詢（藥名／成分名）、
   最新公告與修正、規定變化時間軸、分章節與歷史年版下載。定期追蹤更新。
2. **家庭醫師照護計畫（家醫計畫）**（`fm.html`）：計畫問答集（QA）查詢、
   計畫本文章節瀏覽、檔案下載。不定期更新——有新版文件時彙入重建即可。

首頁 `index.html` 為各政策入口。

## 專案結構

```
├── docs/                 # 靜態查詢站（可直接用 GitHub Pages 發布 /docs）
│   ├── index.html        # 首頁（政策入口）
│   ├── drug.html/.js     # 藥品給付規定（給付規定查詢、公告、時間軸、章節、歷史）
│   ├── fm.html/.js       # 家醫計畫（問答集查詢、計畫全文、檔案下載）
│   ├── style.css
│   └── data/             # 前端讀取的 JSON 資料集
│       ├── announcements.json  # 法規公告（主旨、發文字號、發文日期、原文連結）
│       ├── chapters.json       # 最新版藥品給付規定（分章節）附件清單
│       ├── history.json        # 歷史年版（96年版～109年版）整份下載
│       └── meta.json           # 資料產生時間與統計
├── scraper/
│   ├── parse_nhi.py      # 健保署網頁（lp 列表頁 / cp 內容頁 / np 節點頁）解析器
│   ├── fetch_live.py     # 直接抓官網（含 Cloudflare 挑戰頁偵測）
│   ├── fetch_wayback.py  # 從 Internet Archive 抓歷史存檔（官網被擋時的備援）
│   ├── build_dataset.py  # 解析 HTML 快取 → 產生 docs/data/*.json
│   ├── extract_rules.py  # 完整版 PDF／章節檔 → 逐條給付規定 rules.json
│   ├── extract_fm.py     # 家醫計畫問答集＋計畫本文 PDF → fm_qa.json / fm_plan.json
│   └── requirements.txt
└── cache/wayback/        # 已抓取的網頁存檔（本次資料集的來源，可重現建置）
```

## 本機預覽

```bash
cd docs && python3 -m http.server 8000
# 開啟 http://localhost:8000
```

## 更新資料

```bash
pip install -r scraper/requirements.txt

# 方式一：直接抓健保署官網（在一般網路環境通常可行）
python3 scraper/fetch_live.py --out cache/live --pages 15

# 方式二：官網被 Cloudflare 擋住時，用 Wayback Machine 存檔補資料
python3 scraper/fetch_wayback.py --out cache/wayback

# 重建資料集
python3 scraper/build_dataset.py cache/live cache/wayback --out docs/data
```

## 給付規定全文查詢（藥名／成分名）

「給付規定查詢」頁籤可用**成分名**（如 `osimertinib`）、**商品名**（如 `Xospata`）或**中文關鍵字**（如 `乾癬`）
搜尋逐條給付規定（**115.7.23 完整版，共 604 條**，涵蓋通則＋第 1～15 節）。

資料建置方式：以官網「整份帶走」的完整 PDF 為首選來源，經 `extract_rules.py`
自動切章並拆解為逐條規定；亦支援以分章節單檔（pdf/odt/doc）建置或補缺章。

```bash
# 首選：完整版 PDF（docs/files/ 內附 115.7.23 版）
python3 scraper/extract_rules.py --full-pdf docs/files/nhi-drug-rules-full-1150723.pdf \
    --out docs/data/rules.json

# 備援：分章節檔案目錄（.doc 需要 antiword：apt install antiword）
python3 scraper/extract_rules.py cache/chapters --out docs/data/rules.json
```

## 資料來源與範圍

- **法規公告／修正規定**：`lp-3258-1.html`（藥品給付規定頁面之「修正規定（自103年4月3日以後生效之公告）」），
  目前資料集共 700+ 筆，涵蓋約 2020-03 ～ 2026-07。
- **最新版分章節**：`np-3397-1.html` 的章節附件（doc/odt/pdf）。
- **歷史年版**：`np-2509-1.html` 的整份歷史檔（96年～109年版）。

### 已知限制

- `www.nhi.gov.tw` 前有 Cloudflare 防護，從資料中心 IP（雲端、CI）抓取常被擋；
  初版資料以 Internet Archive 存檔建置，**民國 115 年 2～6 月**的公告因存檔覆蓋不全而有缺口，
  在可直連官網的環境執行 `fetch_live.py` 後重建即可補齊。
- 章節清單目前取自 2024-02 存檔（前端已標示），同樣可用 `fetch_live.py` 更新。
- 本站僅供參考，實際給付規定以健保署公告為準。

## 家醫計畫資料更新

家醫計畫不需定期追蹤。取得新版問答集或計畫本文 PDF 後：

```bash
python3 scraper/extract_fm.py --qa-pdf 問答集.pdf --plan-pdf 計畫本文.pdf \
    --qa-file <docs/files 下的問答集檔名> --plan-file <計畫本文檔名> --out docs/data
```
