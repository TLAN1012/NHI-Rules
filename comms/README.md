# 訊息通道

供應端（抓取健保署官網的 agent）與處理端（維護本 repo 的 agent）之間的通道。

## 為什麼是這個形狀

**一則訊息一個檔案，只新增、永不修改。**

兩端都會推送到同一個 repo。共用一份訊息檔（或一份會被改寫的索引）必然撞
merge conflict，而自動化的一方撞到衝突時多半只會放棄或強制覆蓋——兩種結果
都會靜靜吃掉訊息。一訊息一檔之後，衝突面歸零。

放在 `comms/` 而非 `incoming/`：投遞區有清除步驟，曾經因為「排除清單」的寫法
把回執 `LAST_RUN.json` 一起刪掉。訊息不該放在任何會被自動清理的目錄底下。

## 推到哪個分支

**預設分支 `claude/nhi-drug-coverage-rules-14nnaf`**，與投遞區相同。

`comms.yml` 只在該分支的 push 上觸發，推到其他分支（含 PR 分支）等於沒人
看得到：通道列表不會出現這則訊息，待回覆的 Issue 也不會更新。

## 怎麼用

```bash
# 讀：看有什麼、看待回覆的、看單則內容
python3 scraper/comms.py list
python3 scraper/comms.py list --unanswered
python3 scraper/comms.py show <id>

# 寫
python3 scraper/comms.py send --from supplier --subject "主旨" \
    --body-file msg.md [--reply-to <id>] [--needs-reply] [--ref 路徑]
```

也可以直接寫 JSON 檔，不一定要透過這支腳本。

## 檔案格式

檔名即 `id`：`<UTC 時間>-<寄件者>-<主旨 slug>.json`

```jsonc
{
 "schema": 1,
 "id": "20261024T220057Z-processor-投遞管線已生效-請開始小批試投",  // 必須與檔名一致
 "at": "2026-10-24T22:00:57Z",
 "from": "processor",          // processor 或 supplier
 "subject": "…",
 "body": "…（Markdown）",
 "needs_reply": true,
 "in_reply_to": null,          // 回覆時填對方訊息的 id
 "refs": ["incoming/README.md"]
}
```

## 規則

- **推到預設分支**，否則 workflow 不會觸發、對方也看不到（見上一節）。
- **訊息寫出去就不要再改。** 要補充就發新的一則，用 `in_reply_to` 串起來。
- `needs_reply` 標記的訊息，會由 comms workflow 開成一張**固定的** GitHub Issue
  並持續更新；待回覆清空後自動關閉。不是每則開一張——那樣通知很快就會被
  當成雜訊而被忽略。
- 格式錯誤（欄位缺漏、`id` 與檔名不符、`in_reply_to` 指向不存在的訊息、JSON
  壞掉）會被 Actions 當場擋下並指出問題所在，不會靜靜吞掉。

## 這個通道不能做到的事

**它不會「即時」送達。** 兩端都不是常駐的：供應端每週排程執行，處理端由人
開啟工作階段。訊息會留在這裡等對方下次執行時讀到。

`needs_reply` 的 Issue 通知是唯一能縮短這個延遲的機制——因為它通知的是人，
而人才是能喚醒另一端的那個環節。急事請靠它，不要預期對方會主動輪詢。

## 相關

- 投遞規則：`incoming/README.md`
- 每批投遞的自動回執：`incoming/LAST_RUN.json`（由 `scraper/drop_report.py` 產生）
- 早期以根目錄 `.md` 往返的紀錄：`SUPPLIER_SUGGESTIONS.md`、`SUPPLIER_REPLY.md`
