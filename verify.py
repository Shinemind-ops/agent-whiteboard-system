#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""白板系統進化包 — 驗證器（v2.0 / E-356 / E-357 / E-358）

用法
----
    python verify.py
    python verify.py --agents "C:\Users\me\AGENTS.md" --whiteboard-dir "C:\me\白板" --hermes-dir "..." --session-id TESTSESSION01

任何一項 FAIL 就代表這項進化未真正落地——尤其第 1 項：
「寫了但沒生效的規則，比沒寫更危險，因為它製造『已經管住了』的假象。」
"""
import argparse, os, sys, io, re, subprocess

SECTIONS = '①②③④⑤⑥⑦⑧⑨⑩⑪'
results = []

def chk(name, ok, detail=''):
    results.append((name, ok, detail))
    print('  [{}] {}'.format('PASS' if ok else 'FAIL', name))
    if detail:
        print('         {}'.format(detail))

def rd(p):
    with io.open(p, 'r', encoding='utf-8', newline='') as f:
        return f.read()

def detect_hermes_dir(cli):
    if cli:
        return cli
    for c in [os.environ.get('HERMES_HOME'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), 'hermes'),
              os.path.join(os.path.expanduser('~'), '.hermes')]:
        if c and os.path.isdir(os.path.join(c, 'skills')):
            return c
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--agents')
    ap.add_argument('--hermes-dir')
    ap.add_argument('--whiteboard-dir')
    ap.add_argument('--session-id', default=os.environ.get('HERMES_SESSION_ID', ''),
                    help='指定要驗的 session；預設讀環境變數 HERMES_SESSION_ID')
    a = ap.parse_args()

    hermes = detect_hermes_dir(a.hermes_dir)
    agents = a.agents or os.path.join(os.path.expanduser('~'), 'AGENTS.md')
    wb = a.whiteboard_dir or os.path.join(os.path.expanduser('~'), '白板')
    sid = a.session_id

    print('=== 白板系統 驗證 v2.0 ===')
    print('  AGENTS.md : {}'.format(agents))
    print('  白板根    : {}'.format(wb))
    print('  hermes    : {}'.format(hermes or '（未找到）'))
    print()

    # --- 1. AGENTS.md 兩段 ---
    ok = os.path.exists(agents)
    chk('AGENTS.md 存在', ok, agents)
    if ok:
        t = rd(agents).replace('\r\n', '\n')
        chk('含 B1「開場：讀自己的白板」', '### B1' in t and '讀自己的白板' in t)
        chk('含「echo $HERMES_SESSION_ID」步驟', 'HERMES_SESSION_ID' in t)
        chk('B1 含機械驗證步驟（跑 verify_whiteboard.py）', 'verify_whiteboard.py' in t)
        chk('含 B5「每輪最後一句：強制更新報告」',
            '每輪最後一句' in t and '強制更新報告' in t)
        chk('B5 含 11 項交代格式（更新／未變）', '未變' in t and '理據' in t)

        # 通用偵測：AGENTS.md 內出現的本機絕對路徑，用戶名必須是「當前用戶」。
        # 刻意不寫死任何具體用戶名——通用工具本身不能洩漏原作者的機器。
        cur_user = (os.environ.get('USERNAME') or os.environ.get('USER') or '').lower()
        foreign = []
        for m in re.finditer(r'[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s`\'"|)\]]+)', t):
            if cur_user and m.group(1).lower() != cur_user:
                foreign.append(m.group(0))
        for m in re.finditer(r'(?<![\w.])/(?:home|Users)/([^/\s`\'"|)\]]+)', t):
            if cur_user and m.group(1).lower() != cur_user:
                foreign.append(m.group(0))
        chk('AGENTS.md 無寫死別人的本機路徑', not foreign,
            ('若 FAIL：發現 ' + ', '.join(sorted(set(foreign))[:3]) + '（應改成 ~ 展開或本機路徑）')
            if foreign else 'AGENTS.md 內路徑全部屬於本機')

    # --- 2. skill ---
    if hermes:
        sk = os.path.join(hermes, 'skills', 'meta', 'whiteboard-system', 'SKILL.md')
        chk('whiteboard-system skill 已安裝', os.path.isfile(sk), sk)
        if os.path.isfile(sk):
            st = rd(sk)
            chk('skill frontmatter name 正確', 'name: whiteboard-system' in st)
            chk('skill 含 11 欄骨架定義',
                all(s in st for s in SECTIONS),
                '缺：' + ''.join(s for s in SECTIONS if s not in st))
            chk('skill 含機械驗證章節', 'verify_whiteboard' in st)
    else:
        chk('whiteboard-system skill 已安裝', False, '找不到 hermes 目錄')

    # --- 3. 驗證器 ---
    if hermes:
        vp = os.path.join(hermes, 'scripts', 'verify_whiteboard.py')
        chk('verify_whiteboard.py 已安裝', os.path.isfile(vp), vp)
        if os.path.isfile(vp):
            try:
                r = subprocess.run([sys.executable, vp, '--help'],
                                   capture_output=True, text=True, timeout=30)
                chk('驗證器可執行（--help 正常）', r.returncode == 0,
                    (r.stderr or '')[:200])
            except Exception as e:
                chk('驗證器可執行（--help 正常）', False, str(e)[:200])
    else:
        chk('verify_whiteboard.py 已安裝', False, '找不到 hermes 目錄')

    # --- 4. 白板庫 ---
    chk('白板根目錄存在', os.path.isdir(wb), wb)
    chk('歸檔子目錄存在', os.path.isdir(os.path.join(wb, '歸檔')))
    chk('白板索引存在', os.path.isfile(os.path.join(wb, '白板索引.md')))
    if os.path.isfile(os.path.join(wb, '白板索引.md')):
        chk('索引含「完整路徑」欄', '完整路徑' in rd(os.path.join(wb, '白板索引.md')))

    # --- 5. 本 session 白板 ---
    if sid:
        f = os.path.join(wb, sid + '.md')
        chk('本 session 白板存在（{}）'.format(sid), os.path.isfile(f), f)
        if os.path.isfile(f):
            t = rd(f)
            chk('白板有檔頭「最後更新」時間戳', '最後更新' in t)
            missing = [s for s in SECTIONS if not re.search(r'^##\s*' + s, t, re.M)]
            chk('白板 11 欄齊全', not missing, '缺：' + ''.join(missing))
            chk('白板無日期流水節（### YYYY-MM-DD 式標題）',
                not re.search(r'^#{2,4}\s*\d{4}-\d{2}-\d{2}', t, re.M),
                '日期流水屬日誌，不屬白板')
    else:
        chk('HERMES_SESSION_ID 可讀', False, '環境變數為空——白板無法定位到具體 session')

    # --- 6. 舊制已退役 ---
    if hermes:
        old = os.path.join(hermes, 'RULES.md')
        if os.path.exists(old):
            chk('RULES.md 已標記退役', '退役' in rd(old),
                '若 FAIL：內容仍在使用，會與 AGENTS.md 打架')
        else:
            chk('RULES.md 已標記退役', True, '（檔案不存在，視為已清）')

    npass = sum(1 for _, ok, _ in results if ok)
    ntot = len(results)
    print('\n{}/{} PASS'.format(npass, ntot))
    if npass < ntot:
        print('結論：❌ 未完成——白板系統未真正生效')
        return 1
    print('結論：✅ 白板系統已生效（開場會真的讀到板，死板由機器抓）')
    return 0

if __name__ == '__main__':
    sys.exit(main())