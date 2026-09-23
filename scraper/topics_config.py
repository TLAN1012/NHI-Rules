"""專區設定：共同擬訂會議、醫療給付改善方案。

獨立成一支且不相依任何網路套件，抓取（fetch_topics）與建置（build_topics）
才能各自使用；建置階段不該因為 requests／curl_cffi 沒裝就跑不起來。
"""

from __future__ import annotations

# key 會寫進資料檔並作為網頁篩選值，改動等於換一組資料，不要隨意更名
TOPICS: dict[str, dict[str, str]] = {
    "meetings": {
        "name": "支付標準與共同擬訂會議",
        "hub": "lp-2771-1.html",
        "kind": "list",  # lp- 列表頁，子頁在表格裡
        "url": "https://www.nhi.gov.tw/ch/lp-2771-1.html",
    },
    "programs": {
        "name": "醫療給付改善方案",
        "hub": "np-2823-1.html",
        "kind": "node",  # np- 節點頁，子頁是連結列表
        "url": "https://www.nhi.gov.tw/ch/np-2823-1.html",
    },
}
