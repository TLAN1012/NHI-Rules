#!/usr/bin/env python3
"""comms.py 的訊息通道測試。

執行：python scraper/test_comms.py

重點在「格式檢查要真的擋得住」：這個通道的另一端是自動化的供應端，
格式壞掉若沒當場被擋下，訊息會安靜地消失或被誤讀，而不是有人來問一句。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMS_PY = ROOT / "scraper" / "comms.py"

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}：預期 {want}，實得 {got}")


def run(comms_dir: pathlib.Path, *argv: str) -> subprocess.CompletedProcess:
    """以暫時的 comms 目錄執行，不碰 repo 內真正的訊息。"""
    script = COMMS_PY.read_text(encoding="utf-8").replace(
        'COMMS = pathlib.Path(__file__).resolve().parent.parent / "comms"',
        f'COMMS = pathlib.Path({str(comms_dir)!r})',
    )
    tmp_script = comms_dir.parent / "comms_under_test.py"
    tmp_script.write_text(script, encoding="utf-8")
    return subprocess.run([sys.executable, str(tmp_script), *argv],
                          capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        comms = pathlib.Path(tmp) / "comms"
        comms.mkdir()

        # 1. 送出與列出
        p = run(comms, "send", "--from", "processor", "--subject", "已登錄新列表頁代號",
                "--body", "lp-XXXX 已加入設定，下次投遞會正常收錄。", "--needs-reply")
        check("送出：結束碼", p.returncode, 0)
        files = sorted(comms.glob("*.json"))
        check("送出：產生一個檔案", len(files), 1)
        msg = json.loads(files[0].read_text(encoding="utf-8"))
        check("送出：id 與檔名一致", msg["id"], files[0].stem)
        check("送出：寄件者", msg["from"], "processor")
        check("送出：needs_reply", msg["needs_reply"], True)
        # 兩端以中文溝通，檔名必須保留主旨才有辨識度
        check("送出：檔名保留中文主旨", "已登錄新列表頁代號" in files[0].name, True)
        print(f"  送出訊息：{files[0].name}")

        p = run(comms, "list", "--unanswered")
        check("待回覆清單：列出該則", msg["id"] in p.stdout, True)

        # 2. 回覆之後就不再是待回覆
        p = run(comms, "send", "--from", "supplier", "--subject", "收到，下週投遞",
                "--body", "已更新抓取清單。", "--reply-to", msg["id"])
        check("回覆：結束碼", p.returncode, 0)
        p = run(comms, "list", "--unanswered")
        check("回覆後：不再列為待回覆", msg["id"] in p.stdout, False)
        print("  回覆後：原訊息自動移出待回覆清單")

        # 3. 格式檢查：正常情況要通過
        p = run(comms, "validate")
        check("格式檢查：正常應通過", p.returncode, 0)

        # 4. 壞掉的訊息要被擋下來，而且要指出哪裡壞
        bad = comms / "20261025T000000Z-supplier-broken.json"
        bad.write_text(json.dumps({
            "schema": 1, "id": "wrong-id", "at": "2026-10-25T00:00:00Z",
            "from": "nobody", "subject": "", "body": "x",
        }, ensure_ascii=False), encoding="utf-8")
        p = run(comms, "validate")
        check("壞訊息：結束碼非 0", p.returncode, 1)
        for expect in ("from", "subject", "id"):
            check(f"壞訊息：指出 {expect} 有問題", expect in p.stdout, True)
        print("  壞訊息：被擋下並指出 from／subject／id 三處問題")

        # 5. 連 JSON 都壞掉時不應整個崩掉，而應回報該檔
        bad.write_text("{ 這不是 JSON", encoding="utf-8")
        p = run(comms, "validate")
        check("JSON 壞掉：結束碼非 0", p.returncode, 1)
        check("JSON 壞掉：指出無法解析", "無法解析" in p.stdout, True)
        bad.unlink()

        # 6. in_reply_to 指向不存在的訊息要被擋：否則對話會斷在沒人發現的地方
        orphan = comms / "20261025T010000Z-supplier-orphan.json"
        orphan.write_text(json.dumps({
            "schema": 1, "id": "20261025T010000Z-supplier-orphan",
            "at": "2026-10-25T01:00:00Z", "from": "supplier",
            "subject": "回覆不存在的訊息", "body": "x",
            "needs_reply": False, "in_reply_to": "20200101T000000Z-processor-nope", "refs": [],
        }, ensure_ascii=False), encoding="utf-8")
        p = run(comms, "validate")
        check("斷鏈回覆：被擋下", p.returncode, 1)
        check("斷鏈回覆：指出 in_reply_to", "in_reply_to" in p.stdout, True)
        print("  斷鏈回覆：指向不存在的訊息會被擋下")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("全部通過 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
