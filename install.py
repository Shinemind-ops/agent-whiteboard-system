#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""白板系統進化包 — 安裝器（v2.0 / E-356 / E-357 / E-358）

把「每輪必讀的開場規則」從不會自動載入的 RULES.md / SESSION-RULES-<id>.md，
搬到唯一會自動注入的 AGENTS.md；為每個 session 建一塊 11 欄骨架白板；
並安裝機械驗證器——白板死活由機器抓，不靠 agent 自覺申報。

用法
----
    python install.py --dry-run          # 只報告會做什麼，不動任何檔（建議先跑）
    python install.py                    # 自動偵測路徑並安裝
    python install.py --agents "C:\\Users\\me\\AGENTS.md" \\
                      --whiteboard-dir "C:\\me\\白板" \\
                      --hermes-dir "C:\\Users\\me\\AppData\\Local\\hermes"

設計原則
--------
1. 冪等：跑幾次結果一樣，已存在的段落／檔案不重複插入。
2. 先備份：任何被改的檔都有 <檔名>.<時間戳>.bak。
3. 不刪東西：只加不改。舊的 RULES.md 由你決定留或刪。
4. 路徑可換：payload 裡寫死的路徑會換成你實際的目錄。
"""
import argparse, os, shutil, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(HERE, 'payload')
def fallback_hermes():
    """找不到 hermes 目錄時的通用推導——絕不寫死任何一部機的路徑。"""
    if sys.platform == 'win32':
        return os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'hermes')
    return os.path.join(os.path.expanduser('~'), '.local', 'share', 'hermes')
STAMP = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

log = []
def say(msg):
    log.append(msg)
    print(msg)

def io_open(p):
    import io
    return io.open(p, 'r', encoding='utf-8', newline='')

def read(p):
    with io_open(p) as f:
        return f.read()

def write(p, s):
    import io
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(s)

def backup(path):
    if not os.path.exists(path):
        return None
    dst = '{}.{}.bak'.format(path, STAMP)
    shutil.copy2(path, dst)
    say('    備份 → {}'.format(dst))
    return dst

def detect_hermes_dir(cli):
    if cli:
        return cli
    for c in [os.environ.get('HERMES_HOME'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), 'hermes'),
              os.path.join(os.path.expanduser('~'), '.hermes')]:
        if c and os.path.isdir(os.path.join(c, 'skills')):
            return c
    return None

def detect_agents(cli):
    if cli:
        return cli
    for c in [os.path.join(os.getcwd(), 'AGENTS.md'),
              os.path.join(os.path.expanduser('~'), 'AGENTS.md')]:
        if os.path.exists(c):
            return c
    return os.path.join(os.getcwd(), 'AGENTS.md')

def extract_section(text, start_marker, end_marker):
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i)
    return text[i:j if j > 0 else len(text)].rstrip('\n')

def first_heading_insert_point(lines):
    """插入點：檔頭第一個 '# ' 標題之後；沒有就 0。"""
    for n, l in enumerate(lines):
        if l.startswith('# '):
            return n + 1
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--agents')
    ap.add_argument('--hermes-dir')
    ap.add_argument('--whiteboard-dir')
    ap.add_argument('--session-id', default=os.environ.get('HERMES_SESSION_ID', ''))
    a = ap.parse_args()

    say('=== 白板系統進化包 安裝器 v2.0（E-356 / E-357 / E-358）===')
    if a.dry_run:
        say('*** DRY RUN：唔會改任何檔 ***')

    hermes = detect_hermes_dir(a.hermes_dir)
    agents = detect_agents(a.agents)
    wb = a.whiteboard_dir or os.path.join(os.path.expanduser('~'), '白板')
    sid = a.session_id or 'unknown_' + STAMP

    say('\n偵測結果')
    say('  hermes 目錄   : {}'.format(hermes or '** 找不到 **'))
    say('  AGENTS.md     : {}{}'.format(agents, '' if os.path.exists(agents) else '（不存在，將新建）'))
    say('  白板根目錄    : {}'.format(wb))
    say('  本 session id : {}'.format(sid))

    # --- 1. 讀 payload ---
    segs = read(os.path.join(PAYLOAD, 'AGENTS-template.md'))
    segB1 = extract_section(segs, '### B1 · 開場', '## 安裝位置') or ''
    segB5 = extract_section(segs, '#### 每輪最後一句', '## 安裝位置') or ''
    segB1 = segB1.split('\n---\n')[0].rstrip()
    segB5 = segB5.split('\n---\n')[0].rstrip()
    if not segB1 or not segB5:
        say('!! payload 缺段落，中止')
        return 2
    segB1 = segB1.replace('<白板根>', wb).replace('<hermes 目錄>', hermes or fallback_hermes())
    segB5 = segB5.replace('<白板根>', wb)
    say('\n[1/6] payload 段落就緒（B1 {} 字、B5 {} 字）'.format(len(segB1), len(segB5)))

    # --- 2. 改 AGENTS.md ---
    say('[2/6] 更新 AGENTS.md')
    cur = read(agents) if os.path.exists(agents) else ''
    cur_lf = cur.replace('\r\n', '\n')
    has_b1 = ('### B1' in cur_lf and '讀自己的白板' in cur_lf)
    has_b5 = ('每輪最後一句' in cur_lf and '強制更新報告' in cur_lf)

    if has_b1 and has_b5:
        say('    已有 B1 + B5 → 跳過（不重複插入）')
    else:
        if not a.dry_run:
            backup(agents)
            body = cur_lf
            if not body.strip():
                body = '# 每輪指路器\n'
            if not has_b1:
                lines = body.split('\n')
                # 有 A/B 結構就插在「## B · 一輪流程」之後，否則插檔頭標題後
                ins = None
                for n, l in enumerate(lines):
                    if l.startswith('## B · 一輪流程'):
                        ins = n + 1
                        break
                if ins is None:
                    ins = first_heading_insert_point(lines)
                while ins < len(lines) and lines[ins].strip() == '':
                    ins += 1
                body = '\n'.join(lines[:ins]) + '\n\n' + segB1 + '\n\n' + '\n'.join(lines[ins:])
                say('    已插入「B1 · 開場：讀自己的白板」')
            if not has_b5:
                lines = body.split('\n')
                ins = None
                for n, l in enumerate(lines):
                    if l.startswith('## 其餘規矩在哪找') or l.startswith('### 其餘規矩在哪找'):
                        ins = n
                        break
                if ins is None:
                    body = body.rstrip('\n') + '\n\n' + segB5 + '\n'
                else:
                    body = '\n'.join(lines[:ins]) + segB5 + '\n\n---\n\n' + '\n'.join(lines[ins:])
                say('    已插入「每輪最後一句：強制更新報告」')
            body = body.replace('\n\n\n\n', '\n\n')
            write(agents, body)
        else:
            say('    （dry-run）會插入 B1 = {} / B5 = {}'.format(not has_b1, not has_b5))

    # --- 3. 裝 skill ---
    say('[3/6] 安裝 whiteboard-system skill')
    if not hermes:
        say('    !! 找不到 hermes 目錄，跳過（用 --hermes-dir 指定）')
    else:
        dst_dir = os.path.join(hermes, 'skills', 'meta', 'whiteboard-system')
        dst = os.path.join(dst_dir, 'SKILL.md')
        if os.path.exists(dst):
            say('    已存在 → 覆蓋前先備份')
            if not a.dry_run:
                backup(dst)
        if not a.dry_run:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(os.path.join(PAYLOAD, 'SKILL.md'), dst)
        say('    → {}'.format(dst))

    # --- 4. 裝驗證器 ---
    say('[4/6] 安裝機械驗證器 verify_whiteboard.py')
    if not hermes:
        say('    !! 找不到 hermes 目錄，跳過')
    else:
        sdir = os.path.join(hermes, 'scripts')
        sdst = os.path.join(sdir, 'verify_whiteboard.py')
        if os.path.exists(sdst):
            say('    已存在 → 覆蓋前先備份')
            if not a.dry_run:
                backup(sdst)
        if not a.dry_run:
            os.makedirs(sdir, exist_ok=True)
            shutil.copy2(os.path.join(PAYLOAD, 'verify_whiteboard.py'), sdst)
        say('    → {}'.format(sdst))
        say('    用途：python "{}" --session $HERMES_SESSION_ID'.format(sdst))

    # --- 5. 建白板庫 ---
    say('[5/6] 建立白板庫')
    wb_file = os.path.join(wb, sid + '.md')
    idx_file = os.path.join(wb, '白板索引.md')
    if not a.dry_run:
        os.makedirs(os.path.join(wb, '歸檔'), exist_ok=True)
        if not os.path.exists(wb_file):
            tpl = read(os.path.join(PAYLOAD, 'template-board.md'))
            now = datetime.datetime.now()
            body = (tpl.replace('<SESSION_ID>', sid)
                       .replace('<YYYY-MM-DD HH:MM>', now.strftime('%Y-%m-%d %H:%M'))
                       .replace('<YYYY-MM-DD>', now.strftime('%Y-%m-%d'))
                       .replace('<白板根>', wb))
            write(wb_file, body)
            say('    新建 11 欄白板 → {}'.format(wb_file))
        else:
            say('    白板已存在 → {}'.format(wb_file))
        if not os.path.exists(idx_file):
            idx = read(os.path.join(PAYLOAD, 'template-index.md')).replace('<白板根>', wb)
            write(idx_file, idx)
            say('    新建索引 → {}'.format(idx_file))
        else:
            say('    索引已存在 → {}'.format(idx_file))

    # --- 6. RULES 退役 ---
    say('[6/6] 檢查舊 RULES.md')
    old_rules = os.path.join(hermes, 'RULES.md') if hermes else None
    if old_rules and os.path.exists(old_rules):
        say('    發現舊 RULES.md（{}）— 內容已遷入 AGENTS.md'.format(old_rules))
        if not a.dry_run:
            backup(old_rules)
            notice = read(os.path.join(PAYLOAD, 'RULES-retirement.md')).replace(
                '<日期>', datetime.date.today().isoformat())
            write(old_rules, notice)
            say('    已改寫成退役公告（原文留 .bak）')
    else:
        say('    無舊 RULES.md，略過')

    say('\n=== 完成 ===' if not a.dry_run else '\n=== DRY RUN 完（冇改任何檔）===')
    say('驗證：python verify.py --agents "{}" --whiteboard-dir "{}" --hermes-dir "{}"'.format(
        agents, wb, hermes or ''))
    return 0

if __name__ == '__main__':
    sys.exit(main())