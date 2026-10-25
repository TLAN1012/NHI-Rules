"""專區設定：共同擬訂會議、醫療給付改善方案。

獨立成一支且不相依任何網路套件，抓取（fetch_topics）與建置（build_topics）
才能各自使用；建置階段不該因為 requests／curl_cffi 沒裝就跑不起來。
"""

from __future__ import annotations

# key 會寫進資料檔並作為網頁篩選值，改動等於換一組資料，不要隨意更名
# hubs 刻意是清單：健保署會把專區搬家並讓舊頁停更（lp-2771 自 114-03-28 起
# 即不再更新，內容移往「支付標準相關法規及規範 > 共同擬訂會議查詢」）。
# 新舊頁並列時兩邊都會被走訪、項目以 cp- 代號去重，換頁期間不會斷資料，
# 也不必改程式——取得新頁代號後加一行即可。
TOPICS: dict[str, dict] = {
    "meetings": {
        "name": "支付標準與共同擬訂會議",
        # np-3720 是官網新位置（舊頁 lp-2771 自 114-03-28 停更）。兩者是不同的樹：
        # lp-2771 直接掛 22 個年度頁 cp-…-2771-1；np-3720 下還有一層年度節點
        # np-…（115年 np-4147、114年 np-3911…），會議頁在再下一層。
        "hubs": ["lp-2771-1.html", "np-3720-1.html"],
        "kind": "list",  # lp- 列表頁，子頁在表格裡
        "url": "https://www.nhi.gov.tw/ch/lp-2771-1.html",
    },
    "programs": {
        "name": "醫療給付改善方案",
        "hubs": ["np-2823-1.html"],
        "kind": "node",  # np- 節點頁，子頁是連結列表
        "url": "https://www.nhi.gov.tw/ch/np-2823-1.html",
    },
}
