#!/usr/bin/env python3
"""為 docs/ 的 CSS／JS 引用加上內容雜湊版本參數（cache busting）。

GitHub Pages 對靜態資源回 `cache-control: max-age=600`，剛部署後 10 分鐘內
瀏覽器仍可能沿用舊的 .js／.css，造成「新版 HTML 配舊版 JS」的錯亂畫面。
本腳本把引用改寫成 `risk.js?v=<內容雜湊>`：內容有變才換網址、才重新下載，
內容沒變則沿用快取。

用法（每次改完前端資源後執行，commit 前）：
    python3 scraper/stamp_assets.py
"""

from __future__ import annotations

import hashlib
import pathlib
import re

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
# 掃描 docs/ 下所有頁面（不寫死清單，新增頁面才不會漏戳版本）
ASSET_RE = re.compile(r'((?:href|src)=")([\w./-]+\.(?:css|js))(?:\?v=[0-9a-f]+)?(")')


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def main() -> int:
    changed = 0
    for page in sorted(DOCS.glob("*.html")):
        name = page.name
        html = page.read_text(encoding="utf-8")

        def stamp(m: re.Match) -> str:
            asset = DOCS / m.group(2)
            if not asset.exists():
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}?v={digest(asset)}{m.group(3)}"

        new = ASSET_RE.sub(stamp, html)
        if new != html:
            page.write_text(new, encoding="utf-8")
            changed += 1
            for m in ASSET_RE.finditer(new):
                print(f"  {name}: {m.group(2)}?v={digest(DOCS / m.group(2))}")
    print(f"完成，更新 {changed} 個頁面")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
