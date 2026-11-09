#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_whiteboard.py — 白板系統機械驗證

不靠 agent 自覺申報。掃白板庫 + state.db，逐塊核五項：

  1. 11 個固定欄存在（骨架完整）
  2. 檔頭「最後更新」vs 該 session 最後回覆時間（死板檢測）
  3. ⑧ 近 5 輪條數（滑動窗口冇爆）
  4. ④ 的鏡像來源路徑檔案存在
  5. 冇日期流水節殘留（`## 2026-...` 式章節）

用法：
  python verify_whiteboard.py                      驗全部
  python verify_whiteboard.py --session <id>       驗單個
  python verify_whiteboard.py --json               機器可讀
  python verify_whiteboard.py --dir <白板夾>        自訂白板夾

退出碼：0 = 全部 PASS；1 = 有 FAIL。
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys

DEFAULT_BOARD_DIR = r"C:\Shinemind\白板"
DEFAULT_DB = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local")), "hermes", "state.db")

LAG_MINUTES = 10   # 白板容許落後最後回覆的分鐘數
STALE_HOURS = 6    # session 沉睡超過此小時數，死板只警告不計 FAIL

REQUIRED_SECTIONS = [
    ("①", "專案專屬規則"),
    ("②", "目標"),
    ("③", "當前專案"),
    ("④", "ToDo List"),
    ("⑤", "任務清單"),
    ("⑥", "已完成"),
    ("⑦", "上一回做了什麼"),
    ("⑧", "近 5 輪對話"),
    ("⑨", "未做"),
    ("⑩", "下下步"),
    ("⑪", "怎麼找回當前狀態"),
]

TS_RE = re.compile(r"最後更新\**\s*[:：]\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})")
DAYFLOW_RE = re.compile(r"^##\s+20\d{2}-\d{2}-\d{2}", re.M)


def last_reply_times(db_path):
    """session_id -> 最後一條 assistant 訊息的 timestamp（unix float）"""
    if not os.path.isfile(db_path):
        return {}, f"狀態庫不存在：{db_path}"
    out = {}
    try:
        uri = "file:%s?mode=ro" % db_path.replace("\\", "/")
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        for sid, ts in conn.execute(
            "SELECT session_id, MAX(timestamp) FROM messages "
            "WHERE role='assistant' AND content IS NOT NULL AND content != '' "
            "GROUP BY session_id"
        ):
            out[sid] = ts
        conn.close()
        return out, None
    except Exception as exc:  # noqa: BLE001
        return {}, "讀狀態庫失敗：%s" % exc


def parse_sections(text):
    """回傳 {欄序號: 該欄起始行號}，只認 `## ①` 這種二級標題"""
    found = {}
    for i, line in enumerate(text.split("\n")):
        m = re.match(r"^##\s*([①②③④⑤⑥⑦⑧⑨⑩⑪])", line)
        if m and m.group(1) not in found:
            found[m.group(1)] = i
    return found


def section_body(text, lines, sym):
    """抽某欄的內容（到下一個 ## 為止）"""
    idx = lines.get(sym)
    if idx is None:
        return ""
    body = []
    for line in text.split("\n")[idx + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def check_board(path, reply_map, now):
    name = os.path.splitext(os.path.basename(path))[0]
    text = open(path, encoding="utf-8", errors="replace", newline="").read()
    fails, notes = [], {}

    # ── 1. 11 欄骨架
    lines = parse_sections(text)
    missing = [sym + " " + label for sym, label in REQUIRED_SECTIONS if sym not in lines]
    notes["sections"] = "%d/11" % (11 - len(missing))
    if missing:
        fails.append("①缺欄 %d 個：%s" % (len(missing), "、".join(missing)))

    # ── 2. 死板檢測：檔頭時間 vs 該 session 最後回覆
    m = TS_RE.search(text)
    board_ts = None
    if not m:
        fails.append("②檔頭冇「最後更新：YYYY-MM-DD HH:MM」")
        notes["freshness"] = "無時間戳"
    else:
        try:
            board_ts = dt.datetime.strptime(re.sub(r"\s+", " ", m.group(1)), "%Y-%m-%d %H:%M")
        except ValueError:
            fails.append("②檔頭時間格式錯：%r" % m.group(1))

    reply_ts = reply_map.get(name)
    if board_ts and reply_ts:
        reply_dt = dt.datetime.fromtimestamp(reply_ts)
        lag_min = (reply_dt - board_ts).total_seconds() / 60
        idle_h = (now - reply_dt).total_seconds() / 3600
        notes["freshness"] = "板 %s ／ 回覆 %s" % (
            board_ts.strftime("%m-%d %H:%M"), reply_dt.strftime("%m-%d %H:%M"))
        if lag_min > LAG_MINUTES:
            if idle_h > STALE_HOURS:
                # session 已沉睡（預設 >6 小時無回覆）——死板警告，不計 FAIL
                notes["freshness"] += "（沉睡 %.0f 小時．降級警告）" % idle_h
            else:
                fails.append("②死板：白板落後最後回覆 %.0f 分鐘（板 %s ／ 回覆 %s）" % (
                    lag_min, board_ts.strftime("%m-%d %H:%M"), reply_dt.strftime("%m-%d %H:%M")))
    elif board_ts:
        notes.setdefault("freshness", "無對話紀錄可比")

    # ── 3. ⑧ 近 5 輪條數
    body = section_body(text, lines, "⑧")
    rows = [l for l in body.split("\n") if re.match(r"^\|\s*-?\d", l.strip())]
    notes["recent5"] = str(len(rows))
    if len(rows) > 5:
        fails.append("③近 5 輪有 %d 條（上限 5）" % len(rows))

    # ── 4. ④ 鏡像來源
    src = re.search(r"ToDo 來源\**[：:]\s*`([^`]+)`", text)
    if src:
        raw = src.group(1).strip()
        notes["mirror"] = raw
        if not os.path.isfile(raw):
            fails.append("④鏡像來源不存在：%s" % raw)
    else:
        if "無（本 session 未開專案）" not in text:
            notes["mirror"] = "未標來源"

    # ── 5. 日期流水節
    flows = DAYFLOW_RE.findall(text)
    notes["dayflow"] = str(len(flows))
    if flows:
        fails.append("⑤日期流水節 %d 個（白板唔做日誌）" % len(flows))

    return {
        "session": name,
        "path": path,
        "pass": not fails,
        "fails": fails,
        "notes": notes,
        "size": os.path.getsize(path),
    }


def main():
    ap = argparse.ArgumentParser(description="白板系統機械驗證")
    ap.add_argument("--session", help="只驗某個 session id")
    ap.add_argument("--dir", default=DEFAULT_BOARD_DIR, help="白板夾")
    ap.add_argument("--db", default=DEFAULT_DB, help="state.db 路徑")
    ap.add_argument("--json", action="store_true", help="JSON 輸出")
    ap.add_argument("--lag", type=int, default=10, help="容許落後分鐘數（預設 10）")
    ap.add_argument("--stale-hours", type=float, default=6, help="session 沉睡超過此小時數，死板降級為警告（預設 6）")
    args = ap.parse_args()

    global TS_RE, LAG_MINUTES, STALE_HOURS  # noqa: PLW0603
    LAG_MINUTES = args.lag
    STALE_HOURS = args.stale_hours
    boards = sorted(
        p for p in glob.glob(os.path.join(args.dir, "*.md"))
        if "索引" not in os.path.basename(p)
    )
    if args.session:
        boards = [p for p in boards if os.path.splitext(os.path.basename(p))[0] == args.session]

    if not boards:
        print("冇搵到白板（夾：%s）" % args.dir)
        return 1

    reply_map, db_err = last_reply_times(args.db)
    now = dt.datetime.now()
    results = [check_board(p, reply_map, now) for p in boards]

    if args.json:
        print(json.dumps({"db_error": db_err, "boards": results}, ensure_ascii=False, indent=2))
        return 0 if all(r["pass"] for r in results) else 1

    print("白板系統驗證 — %s" % now.strftime("%Y-%m-%d %H:%M"))
    if db_err:
        print("⚠ %s（死板檢測降級）" % db_err)
    print("=" * 68)
    for r in results:
        mark = "✅ PASS" if r["pass"] else "❌ FAIL (%d)" % len(r["fails"])
        n = r["notes"]
        print("\n█ %s  %s  [%d B]" % (r["session"], mark, r["size"]))
        print("   欄位 %s｜時效 %s｜近5輪 %s｜鏡像 %s｜流水節 %s" % (
            n.get("sections", "?"), n.get("freshness", "?"),
            n.get("recent5", "?"), n.get("mirror", "-"), n.get("dayflow", "?")))
        for f in r["fails"]:
            print("   ✗ %s" % f)

    passed = sum(1 for r in results if r["pass"])
    print("\n" + "=" * 68)
    print("總計：%d/%d PASS" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())