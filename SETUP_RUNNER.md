# 任務：在這台機器安裝 GitHub Actions self-hosted runner（NHI-Rules 專案）

> 這份文件是給本地 Claude Code 的完整任務說明。請依序執行，每步驟驗證後再繼續。
> 過程中需要使用者提供一次性註冊 token（見第 3 步），其餘皆可自動完成。

## 背景（為什麼要做這件事）

- Repo：`TLAN1012/NHI-Rules`（公開），是健保政策查詢站，資料來自健保署官網
  `www.nhi.gov.tw`。
- 健保署前有 Cloudflare 防護：**資料中心 IP（GitHub 雲端 runner、任何雲主機）一律被
  互動式驗證擋下**（已實測 plain curl／RSS／真實瀏覽器皆不通）；**住宅／機構 IP 可正常
  存取**。
- 因此 repo 內已備好 `.github/workflows/update-data-selfhosted.yml`：排程由 GitHub
  管理（每日台北 08:30），執行在本機 runner ——本機的住宅 IP 負責直抓官網，抓完自動
  commit 資料並重新部署網站。
- 這台機器是常開的本地 server，適合當 runner。

## 你要達成的最終狀態

1. GitHub Actions self-hosted runner 在本機以**系統服務**方式常駐執行
   （開機自動啟動、關掉終端機不受影響）。
2. Repo 的 Runners 頁面顯示該 runner 為 Idle（綠色）。
3. 手動觸發 `update-data-selfhosted.yml` 一次，確認能直抓健保署官網並成功
   完成（有無新資料皆可，重點是 fetch 步驟不被 Cloudflare 擋）。

## 步驟

### 1. 環境檢查

```bash
git --version
python3 --version          # 需 3.10+
python3 -m pip --version
curl --version
uname -m                   # 記下架構：x86_64 → x64；arm64/aarch64 → arm64
```

缺什麼就先裝（macOS 用 xcode-select/brew；Ubuntu 用 apt）。
另外先驗證這台機器確實能直達健保署（這是整件事的前提）：

```bash
curl -s -o /tmp/nhi-test.html -w "%{http_code}\n" \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" \
  "https://www.nhi.gov.tw/ch/lp-3258-1.html"
grep -c "發文字號" /tmp/nhi-test.html
```

HTTP 200 且 grep 到「發文字號」＝可直達，繼續。若出現 "Just a moment" 或 403，
停下來回報使用者（代表這條網路也被擋，裝 runner 沒有意義）。

### 2. 建立 runner 目錄並下載 runner 程式

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
```

到 https://github.com/actions/runner/releases 取得最新版號，下載對應 OS/架構的
tarball 並解壓（以下以 Linux x64、版本 2.321.0 為例，請替換為實際最新版）：

```bash
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-linux-x64-2.321.0.tar.gz
tar xzf actions-runner.tar.gz
```

（macOS 用 `actions-runner-osx-x64` 或 `-osx-arm64`；Apple Silicon 選 arm64。）

### 3. 取得註冊 token（需要使用者幫忙，一次性）

註冊 token 需要 repo 管理權限，有兩種取法：

**方法 A（若本機已有 `gh` CLI 且已登入 TLAN1012 帳號）：**
```bash
gh api -X POST repos/TLAN1012/NHI-Rules/actions/runners/registration-token --jq .token
```

**方法 B（手動）：** 請使用者開啟
https://github.com/TLAN1012/NHI-Rules/settings/actions/runners/new
頁面上 Configure 區塊會有 `--token XXXX` 字樣，請使用者把 token 貼給你。
（token 效期一小時，拿到後盡快用。）

### 4. 註冊 runner

```bash
cd ~/actions-runner
./config.sh --url https://github.com/TLAN1012/NHI-Rules --token <上一步的TOKEN> \
  --name nhi-local --labels self-hosted --unattended
```

`--unattended` 會用預設值完成設定，不需互動。

### 5. 安裝為系統服務（關鍵步驟）

```bash
# Linux（systemd）與 macOS（launchd）皆適用：
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # 應顯示 active / running
```

若 `svc.sh install` 因權限或環境失敗，Linux 備援方案是手寫 systemd unit
（ExecStart 指向 `~/actions-runner/run.sh`，enable + start）。

### 6. 驗證 runner 上線

```bash
gh api repos/TLAN1012/NHI-Rules/actions/runners --jq '.runners[] | {name, status}'
# 沒有 gh 的話，請使用者看網頁：Settings → Actions → Runners 應顯示 nhi-local (Idle)
```

### 7. 觸發一次資料更新並驗證

```bash
gh workflow run update-data-selfhosted.yml --repo TLAN1012/NHI-Rules \
  --ref claude/nhi-drug-coverage-rules-14nnaf
sleep 20
gh run list --repo TLAN1012/NHI-Rules --workflow=update-data-selfhosted.yml --limit 1
gh run watch --repo TLAN1012/NHI-Rules $(gh run list --repo TLAN1012/NHI-Rules \
  --workflow=update-data-selfhosted.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

（沒有 gh 就請使用者到 Actions 頁面手動按 Run workflow，選
`claude/nhi-drug-coverage-rules-14nnaf` 分支。）

成功標準：
- 「Fetch from NHI website (residential IP)」步驟成功（log 有多個 `ok  lp-3258-1.html?...`）
- 若有新資料，會出現 bot commit `chore(data): 自動更新健保公告資料（official site, self-hosted）`
  且網站 https://tlan1012.github.io/NHI-Rules/ 幾分鐘後更新

### 8. 安全設定提醒（請轉告使用者在網頁完成）

公開 repo 搭配 self-hosted runner，務必到
**Settings → Actions → General → Fork pull request workflows from outside collaborators**
勾選 **Require approval for all outside collaborators**。
這確保陌生人 fork 發 PR 的程式碼不會未經核准就跑在這台機器上。
（若 `gh` 權限足夠，也可嘗試以 API 設定；失敗就請使用者手動。）

## 注意事項

- workflow 會在此機器執行 `pip install --user -r scraper/requirements.txt`
  （只有 requests 與 beautifulsoup4，很輕）。
- runner 工作目錄在 `~/actions-runner/_work/`，磁碟佔用約數十 MB。
- 抓取行為：每日一次、約 20 個 HTTP 請求、間隔 1 秒，對健保署負擔極低。
- 若日後要移除：`sudo ./svc.sh stop && sudo ./svc.sh uninstall`，再到 Runners
  頁面 Remove，或 `./config.sh remove --token <removal-token>`。

## 完成後回報

請總結回報：runner 名稱與狀態、第一次 workflow 執行結果（fetch 是否直達官網、
有無新增資料 commit）、以及安全設定是否已完成。
