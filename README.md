# 健保政策查詢站（NHI-Rules）

台灣全民健保各項政策公告的整理與查詢站（公告查詢性質，不涉及治療建議）。目前收錄：

1. **藥品給付規定**（`drug.html`）：逐條給付規定全文查詢（藥名／成分名）、
   最新公告與修正、規定變化時間軸、分章節與歷史年版下載。定期追蹤更新。
2. **家庭醫師照護計畫（家醫計畫）**（`fm.html`）：計畫問答集（QA）查詢、
   計畫本文章節瀏覽、檔案下載。不定期更新——有新版文件時彙入重建即可。
3. **風險計算機**（`risk.html`）：ASCVD 風險等級評估（降膽固醇藥物給付規定表一，
   健保審字第1150671962號、115.9.1 生效）。勾選臨床條件自動判定風險等級與
   給付門檻/血脂目標，一鍵複製評估結果至剪貼簿供病歷記載。
   給付條文的修訂標示由 `docs/data/rule_updates.json` 維護。

首頁 `index.html` 為各政策入口。

另有 **共擬會議與給付改善方案異動**（`topics.html`）：醫療服務給付項目及支付標準
共同擬訂會議、醫療給付改善方案兩個專區的異動追蹤。除了新上架項目，同一項目
「換了新版計畫書」或「補上會議紀錄」也會列出——這類更新不改標題，只比對清單
看不出來，故比對做到**附件層級**。每週更新。

此頁**刻意不放在首頁卡片區**：共擬會議的議程與會議紀錄不適合被當成公開賣點推播。
入口只在首頁頁尾一行低調連結，頁面本身掛 `<meta name="robots" content="noindex, nofollow">`
不進搜尋引擎索引。

> 注意這只是「不主動曝光」，**不是存取控制**——本頁仍可由任何知道網址的人開啟。
> 若需要真正的存取限制，靜態站（GitHub Pages）做不到，得改放有登入機制的地方。
>
> 這裡不用 `robots.txt` 擋：`Disallow` 反而會把路徑寫進人人可讀的檔案，
> 且被擋爬的頁面讀不到 `noindex`，效果與目的相反。

## 專案結構

```
├── docs/                 # 靜態查詢站（可直接用 GitHub Pages 發布 /docs）
│   ├── index.html        # 首頁（政策入口）
│   ├── drug.html/.js     # 藥品給付規定（給付規定查詢、公告、時間軸、章節、歷史）
│   ├── fm.html/.js       # 家醫計畫（問答集查詢、計畫全文、檔案下載）
│   ├── topics.html/.js   # 共擬會議／改善方案異動（變動紀錄、各專區項目與附件）
│   ├── style.css
│   └── data/             # 前端讀取的 JSON 資料集
│       ├── announcements.json  # 法規公告（主旨、發文字號、發文日期、原文連結）
│       ├── chapters.json       # 最新版藥品給付規定（分章節）附件清單
│       ├── history.json        # 歷史年版（96年版～109年版）整份下載
│       ├── topics.json         # 共擬會議／改善方案的項目與附件（含附件指紋）
│       ├── topic_changes.json  # 上述兩專區的變動紀錄（新增／附件更新／下架）
│       └── meta.json           # 資料產生時間與統計
├── scraper/
│   ├── parse_nhi.py      # 健保署網頁（lp 列表頁 / cp 內容頁 / np 節點頁）解析器
│   ├── fetch_live.py     # 直接抓官網（含 Cloudflare 挑戰頁偵測）
│   ├── fetch_wayback.py  # 從 Internet Archive 抓歷史存檔（官網被擋時的備援）
│   ├── build_dataset.py  # 解析 HTML 快取 → 產生 docs/data/*.json
│   ├── topics_config.py  # 共擬會議／改善方案的專區設定（不相依網路套件）
│   ├── fetch_topics.py   # 抓上述兩專區的 hub 頁與子頁
│   ├── ingest_topics.py  # 把別處抓好的原始 HTML 匯入成快取（繞過 Cloudflare）
│   ├── build_topics.py   # 解析兩專區 → topics.json ＋ 附件層級的變動比對
│   ├── test_build_dataset.py  # 來源優先序測試
│   ├── test_build_topics.py   # 變動偵測測試
│   ├── test_ingest_topics.py  # 外部 HTML 匯入測試
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

# 共擬會議／改善方案（需能直連官網；抓下的 HTML 存 cache/topics/，
# 不要餵給 build_dataset.py，其列表頁會被誤判成法規公告）
python3 scraper/fetch_topics.py --out cache/topics
python3 scraper/build_topics.py cache/topics --out docs/data

# 或者：頁面已由別處（會開瀏覽器的 bot、人工另存）取得時，改用匯入
python3 scraper/ingest_topics.py <存放原始 HTML 的目錄> --out cache/topics
python3 scraper/build_topics.py cache/topics --out docs/data
```

### 由外部來源匯入頁面

健保署官網對資料中心 IP 一律出 Cloudflare 挑戰頁，雲端／CI 環境抓不到。若已有人
（或會開瀏覽器的 bot）把頁面存下來，用 `ingest_topics.py` 匯入即可，不必在受限
環境裡跟 Cloudflare 周旋。

需要的是**原始 HTML（頁面原始碼）**，不是轉好的 Markdown 或 PDF——解析器讀的是
`section.fileDownload`、`span.fileType`、表格的 `<thead>` 這些結構，轉成 Markdown
後這些資訊已經被壓掉了。

要存哪些頁：

| 專區 | hub | 還要存 |
|---|---|---|
| 共擬會議 | `lp-2771-1.html`（含分頁 `?pi=N&ps=60`） | 表格裡每一列連到的 `cp-` 頁 |
| 改善方案 | `np-2823-1.html` | 其下子分類 `np-` 頁，以及子分類底下的 `cp-` 方案頁 |

附件（會議紀錄、計畫書、問答集）**不必下載**——資料集只記錄檔名、類型、大小與
官網連結，前端也是直接連到官網原始檔。

檔名不拘：匯入時會從 `<link rel=canonical>`／`og:url`／檔名裡的頁面代號自行判斷
是哪一頁。專區歸屬則是從 hub 沿連結走出來的——改善方案的方案頁帶的是子分類代號
而非 hub 代號，用網址規則比對會整批歸錯。沒被任何 hub 連到的檔案會列在
`_fetch_report.json` 的 `unassigned`，不會靜靜吞掉。

## 測試

```bash
python3 scraper/test_build_dataset.py   # 來源優先序（live / wayback / 既有資料）
python3 scraper/test_build_topics.py    # 變動偵測（新增／附件更新／下架／抓取不完整）
python3 scraper/test_ingest_topics.py   # 外部 HTML 匯入（專區歸屬、未歸入者回報）
```

兩支都不需網路。`build_dataset.py` 的來源比較曾因直接比字串而讓 Wayback 存檔
永遠勝過官網即時抓取（整份給付規定一度停在一年前的版本且無人察覺），故以測試釘住。

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

### 自動更新（GitHub Actions）

- `update-data.yml`：每日台北 08:00 於 GitHub 雲端 runner 執行。經實測（2026-08），
  健保署 Cloudflare 對資料中心 IP 一律出互動挑戰頁（plain curl／RSS／真實瀏覽器皆同），
  故雲端版以 **Wayback Machine 為資料源**：自動抓新存檔、比對、有變化才 commit 並重佈網站。
- `update-data-selfhosted.yml`：跑在 **self-hosted runner**（你自己網路內的電腦，
  住宅 IP 可正常通過 Cloudflare）→ 直抓官網最新資料。兩班排程：
  - 每日台北 08:30：藥品給付規定與法規公告
  - 每週六台北 16:00：同上，另加抓共擬會議／改善方案兩個專區並比對變動
    （這兩區需逐頁走訪子頁才拿得到附件，每日抓對官網是不必要的負擔）
  安裝方式見該 workflow 檔內註解；未安裝前不影響其他流程。
- `probe-sources.yml`：資料源可及性探測（手動觸發），佐證上述結論。

### 已知限制

- `www.nhi.gov.tw` 前有 Cloudflare 防護，從資料中心 IP（雲端、CI）抓取常被擋；
  初版資料以 Internet Archive 存檔建置，**民國 115 年 2～6 月**的公告因存檔覆蓋不全而有缺口，
  在可直連官網的環境執行 `fetch_live.py` 後重建即可補齊。
- 章節清單目前仍取自網頁存檔（前端已標示），self-hosted runner 下次直抓官網後即會換成即時版。
- 共擬會議／改善方案的頁面解析以健保署共通版型撰寫，並以表頭文字對應表格欄位
  （各專區欄位不同，不可用固定欄位位置）；**尚未對真實頁面驗證過**。首次以
  self-hosted runner 實抓或以 `ingest_topics.py` 匯入後，應檢查 `topics.json`
  的項目數與附件是否合理。
- 本站僅供參考，實際給付規定以健保署公告為準。

## 家醫計畫資料更新

家醫計畫不需定期追蹤。取得新版問答集或計畫本文 PDF 後：

```bash
python3 scraper/extract_fm.py --qa-pdf 問答集.pdf --plan-pdf 計畫本文.pdf \
    --qa-file <docs/files 下的問答集檔名> --plan-file <計畫本文檔名> --out docs/data
```
