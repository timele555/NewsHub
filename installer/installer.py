"""NewsHub 安装器 —— 向导 / 静默安装 / 卸载 三合一（单文件 exe）。\n\n用法：\n  NewsHub-Setup.exe                  交互向导（DPI 清晰现代界面）\n  NewsHub-Setup.exe /S [目标目录]     静默安装（默认 %LocalAppData%\\Programs\\NewsHub）\n  NewsHub-Setup.exe /U [安装目录]     卸载\n  本 exe 改名 UNINSTALL.exe 放入安装目录即为卸载器（双击确认后卸载）。\n\n行为约定：\n- payload 打包在本 exe 内；升级/重装不覆盖已有 config.json；\n- 全程仅写 HKCU 与用户目录，不需要管理员；\n- 卸载自删采用「隔离改名 + 定向清扫」，绝不误伤同路径的新装。\n"""
import ctypes
import os
import shutil
import subprocess
import threading
import sys
import tempfile
import winreg
from datetime import datetime
APP_NAME = 'NewsHub'
EXE_NAME = 'NewsHub.exe'
RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
RUN_NAME = 'NewsHub'
INI_NAME = 'uninstall.ini'
LOG_LINES = []
def _log(msg):
    LOG_LINES.append(str(msg))
    try:
        print(msg)
    except Exception:
        return None
def _logfile():
    try:
        with open(os.path.join(tempfile.gettempdir(), 'newshub_setup.log'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(LOG_LINES))
    except Exception:
        return None
def payload_dir():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'payload')
def self_exe():
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    else:
        return os.path.abspath(__file__)
def default_target():
    return os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')), 'Programs', APP_NAME)
def local_drives():
    out = []
    for c in 'CDEFGHIJKLMNOPQRSTUVWXYZAB':
        d = f'{c}:\\'
        if os.path.exists(d):
            out.append(d)
    return out
def drive_free_gb(drive):
    free = ctypes.c_ulonglong()
    try:
        free = ctypes.c_ulonglong()
        if ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(drive), None, None, ctypes.byref(free)):
            return free.value / 1073741824
        return -1
    except Exception:
        return -1
_BAD_CHARS = '<>|\"?*'
def normalize_target(raw):
    """路径清洗：去引号/首尾空白/结尾斜杠，统一反斜杠 → (ok, path, err)。"""
    p = str(raw or '').strip().strip('\"').strip()
    if not p:
        return (False, '', '路径不能为空')
    p = p.replace('/', '\\')
    while len(p) > 3 and p.endswith('\\'):
        p = p.rstrip('\\')
    drive, rest = os.path.splitdrive(p)
    if not drive or ':' not in drive:
        return (False, p, '缺少盘符（如 D:\\NewsHub）')
    if any((ch in rest for ch in _BAD_CHARS)):
        return (False, p, '路径含非法字符  < > | " ? *')
    return (True, p, '')
def validate_target(raw):
    """格式合法 + 盘存在 + 可创建可写 → (ok, path, err)。"""
    ok, p, err = normalize_target(raw)
    if not ok:
        return (False, p, err)
    if not os.path.exists(os.path.splitdrive(p)[0] + '\\'):
        return (False, p, f'目标盘 {os.path.splitdrive(p)[0]} 不存在')
    try:
        os.makedirs(p, exist_ok=True)
        probe = os.path.join(p, '.write_probe')
        with open(probe, 'w') as f:
            f.write('ok')
        os.remove(probe)
    except OSError as e:
        return (False, p, f'目录不可写（{e}）')
    return (True, p, '')
def copy_payload(target):
    """复制 payload → 目标目录（用户数据优先：已有 config.json 时配置类文件跳过）。"""
    src = payload_dir()
    if not os.path.isdir(src):
        raise RuntimeError(f'安装包内缺少 payload（{src}）——发布包不完整')
    os.makedirs(target, exist_ok=True)
    n = 0
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dst_root = target if rel == '.' else os.path.join(target, rel)
        os.makedirs(dst_root, exist_ok=True)
        for fn in files:
            if fn in ('config.json', 'config.template.json', 'config.user.json') and os.path.isfile(os.path.join(target, 'config.json')):
                continue
            shutil.copy2(os.path.join(root, fn), os.path.join(dst_root, fn))
            n += 1
    cfg = os.path.join(target, 'config.json')
    if not os.path.isfile(cfg):
        for cand in ['config.user.json', 'config.template.json']:
            tpl = os.path.join(target, cand)
            if os.path.isfile(tpl):
                shutil.copy2(tpl, cfg)
                _log(f'[config] 初始化自 {cand}')
                break
    _log(f'[copy] {n} 个文件 → {target}')
    return n
def write_uninstall_ini(target):
    with open(os.path.join(target, INI_NAME), 'w', encoding='utf-8') as f:
        f.write(f'[install]\ndir={target}\n')
def deploy_uninstaller(target):
    if getattr(sys, 'frozen', False):
        dst = os.path.join(target, 'UNINSTALL.exe')
        shutil.copy2(self_exe(), dst)
        _log(f'[uninstaller] {dst}')
def register(target):
    exe = os.path.join(target, EXE_NAME)
    if not os.path.isfile(exe):
        raise RuntimeError(f'安装不完整：缺少 {exe}')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{exe}"')
    home = os.path.expanduser('~')
    lnks = [os.path.join(home, 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs', f'{APP_NAME}.lnk'), os.path.join(home, 'Desktop', f'{APP_NAME}.lnk')]
    ps = ';'.join((f"$lk=$ws.CreateShortcut('{p}');$lk.TargetPath='{exe}';$lk.WorkingDirectory='{target}';$lk.IconLocation='{exe},0';$lk.Save()" for p in lnks))
    subprocess.run(['powershell', '-NoProfile', '-Command', f'$ws = New-Object -ComObject WScript.Shell;{ps}'], capture_output=True, timeout=60, creationflags=134217728)
    _log('[register] 自启 + 开始菜单/桌面快捷方式')
    return exe
def unregister():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
        _log('[unregister] 自启注册已移除')
    except OSError:
        pass
    home = os.path.expanduser('~')
    for p in (os.path.join(home, 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs', f'{APP_NAME}.lnk'), os.path.join(home, 'Desktop', f'{APP_NAME}.lnk')):
        try:
            os.remove(p)
            _log(f'[unregister] 已删 {p}')
        except OSError:
            pass
def post_install_check(target):
    exe = os.path.join(target, EXE_NAME)
    try:
        r = subprocess.run([exe, '--doctor-quick'], capture_output=True, timeout=120, cwd=target, creationflags=134217728)
        report = r.stdout.decode('utf-8', 'replace')
        sc = os.path.join(target, 'data', 'logs', 'selfcheck.txt')
        if not report.strip() and os.path.isfile(sc):
            with open(sc, encoding='utf-8-sig') as f:
                report = f.read()
        ok = r.returncode == 0
        _log(f'[selfcheck] exit={r.returncode}')
        return (ok, report if report else '（自检完成，无输出）')
    except Exception as e:
        return (False, f'自检执行失败：{e}')
def _dir_is_newshub(target):
    return os.path.isfile(os.path.join(target, EXE_NAME)) and os.path.isdir(os.path.join(target, '_internal'))
def do_uninstall(target):
    if not target or not _dir_is_newshub(target):
        _log(f'[uninstall] 目录不是 NewsHub 安装目录，拒绝删除：{target}')
        return False
    subprocess.run(['taskkill', '/IM', EXE_NAME, '/F'], capture_output=True, creationflags=134217728)
    unregister()
    me = self_exe()
    if getattr(sys, 'frozen', False) and os.path.normcase(os.path.dirname(me)) == os.path.normcase(target):
        for root, dirs, files in os.walk(target, topdown=False):
            for fn in files:
                fp = os.path.join(root, fn)
                if os.path.normcase(fp) == os.path.normcase(me):
                    continue
                try:
                    os.remove(fp)
                except OSError:
                    pass
            for dn in dirs:
                try:
                    os.rmdir(os.path.join(root, dn))
                except OSError:
                    pass
        old = target.rstrip('\\/') + '.old-' + datetime.now().strftime('%Y%m%d%H%M%S')
        try:
            os.rename(target, old)
        except OSError:
            _log(f'[uninstall] 已清空 {target}（个别文件被占用，目录请稍后手动删除）')
            return True
        try:
            if os.path.isfile(me):
                ctypes.windll.kernel32.MoveFileExW(me, None, 4)
        except Exception:
            pass
        subprocess.Popen(['cmd', '/c', f'ping -n 4 127.0.0.1 >nul & rmdir /s /q "{old}"'], creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
        _log(f'[uninstall] 已卸载 {target}（隔离残壳 {old} 将自动清扫）')
        return True
    else:
        shutil.rmtree(target, ignore_errors=True)
        _log(f'[uninstall] 已删除 {target}')
        return True
def read_ini_target():
    base = os.path.dirname(self_exe())
    try:
        with open(os.path.join(base, INI_NAME), encoding='utf-8-sig') as f:
            for line in f:
                if line.lower().startswith('dir='):
                    return line[4:].strip()
    except Exception:
        return ''
    return ''
def resolve_uninstall_target(explicit=None):
    """显式参数 > 自身所在目录 > ini 兜底。"""
    if explicit:
        return os.path.abspath(explicit)
    me_dir = os.path.dirname(self_exe())
    if _dir_is_newshub(me_dir):
        return me_dir
    ini = read_ini_target()
    return os.path.abspath(ini) if ini else ''
def do_silent(raw_target):
    okv, target, err = validate_target(raw_target)
    _log(f'== NewsHub 静默安装 → {target} ==')
    if not okv:
        _log(f'[FAIL] {err}')
        return 1
    copy_payload(target)
    write_uninstall_ini(target)
    deploy_uninstaller(target)
    register(target)
    ok, report = post_install_check(target)
    if not ok:
        _log(f'[selfcheck][FAIL] {report[:200]}')
        return 1
    _log('[done] 静默安装完成')
    return 0
def run_gui():
    """安装向导：欢迎 → 路径选择 → 安装 → 完成，四步引导。"""
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.title(f'{APP_NAME} 安装向导')
    root.geometry('760x540')
    root.minsize(680, 480)
    state = {'target': default_target(), 'launched': False, 'done': False}
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    body = tk.Frame(root)
    body.grid(row=0, column=0, sticky='nsew', padx=18, pady=(14, 6))
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)
    foot = tk.Frame(root)
    foot.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 12))
    status = tk.Label(foot, text='', anchor='w', fg='#555')
    status.pack(side='left')
    def set_step(msg):
        status.config(text=msg)
        root.update_idletasks()
    back = tk.Button(foot, text='< 上一步', width=10, state='disabled')
    nxt = tk.Button(foot, text='下一步 >', width=10)
    nxt.pack(side='right')
    back.pack(side='right', padx=8)
    pages = {}
    def show(name):
        for p in pages.values():
            p.pack_forget()
        pages[name].pack(fill='both', expand=True)
    pw = tk.Frame(body)
    pages['welcome'] = pw
    tk.Label(pw, text=f'欢迎使用 {APP_NAME} 安装向导', font=('Microsoft YaHei', 16, 'bold')).pack(pady=(60, 8))
    tk.Label(pw, text='将引导你完成安装。建议安装到非系统盘（如 D:\\NewsHub）。', fg='#555').pack()
    pp = tk.Frame(body)
    pp.columnconfigure(0, weight=1)
    pages['path'] = pp
    tk.Label(pp, text='选择安装位置', font=('Microsoft YaHei', 13, 'bold')).grid(row=0, column=0, sticky='w', pady=(8, 6))
    prow = tk.Frame(pp)
    prow.grid(row=1, column=0, sticky='ew')
    prow.columnconfigure(0, weight=1)
    var_target = tk.StringVar(value=state['target'])
    ent = tk.Entry(prow, textvariable=var_target, font=('Consolas', 11))
    ent.grid(row=0, column=0, sticky='ew')
    def browse():
        d = filedialog.askdirectory(initialdir=var_target.get() or 'D:/')
        if d:
            var_target.set(os.path.abspath(d))
    tk.Button(prow, text='浏览…', command=browse).grid(row=0, column=1, padx=(8, 0))
    drvrow = tk.Frame(pp)
    drvrow.grid(row=2, column=0, sticky='w', pady=6)
    preview = tk.Label(pp, text='', fg='#555', justify='left', anchor='w')
    preview.grid(row=3, column=0, sticky='ew')
    def refresh_preview(*_):
        t = var_target.get()
        okv, _, err = validate_target(t)
        if okv:
            gb = drive_free_gb(os.path.splitdrive(t)[0] + '\\')
            preview.config(text=f'✅ 可安装 · 目标盘剩余约 {gb:.1f} GB')
        else:
            preview.config(text='⚠️ ' + err)
    var_target.trace_add('write', refresh_preview)
    for c in local_drives()[:8]:
        tk.Button(drvrow, text=c, width=6, command=lambda cc=c: var_target.set(os.path.join(cc, APP_NAME))).pack(side='left', padx=3)
    pi = tk.Frame(body)
    pi.columnconfigure(0, weight=1)
    pi.rowconfigure(0, weight=1)
    pages['install'] = pi
    tk.Label(pi, text='正在安装…', font=('Microsoft YaHei', 13, 'bold')).grid(row=1, column=0, sticky='w')
    logbox = tk.Text(pi, height=18, font=('Consolas', 9), state='disabled', bg='#0f172a', fg='#dbe4f0')
    logbox.grid(row=0, column=0, sticky='nsew', pady=(8, 6))
    def say(msg):
        LOG_LINES.append(str(msg))
        logbox.config(state='normal')
        logbox.insert('end', str(msg) + '\n')
        logbox.see('end')
        logbox.config(state='disabled')
        root.update_idletasks()
    pd = tk.Frame(body)
    pages['done'] = pd
    tk.Label(pd, text='🎉 安装完成', font=('Microsoft YaHei', 16, 'bold')).pack(pady=(40, 8))
    var_launch = tk.BooleanVar(value=True)
    tk.Checkbutton(pd, text=f'立即运行 {APP_NAME}', variable=var_launch).pack()
    def do_install():
        def worker():
            try:
                def step_say(msg):
                    root.after(0, say, msg)
                target = state['target']
                root.after(0, set_step, '复制文件…')
                n = copy_payload(target)
                root.after(0, say, f'[copy] {n} 个文件 → {target}')
                root.after(0, set_step, '写入卸载信息…')
                write_uninstall_ini(target)
                deploy_uninstaller(target)
                root.after(0, set_step, '注册自启与快捷方式…')
                register(target)
                root.after(0, set_step, '自检…')
                ok, report = post_install_check(target)
                for ln in (report or '').splitlines()[:12]:
                    root.after(0, say, ln)
                if not ok:
                    root.after(0, messagebox.showerror, APP_NAME, '安装后自检未通过，详见日志。')
                state['done'] = True
                root.after(0, show, 'done')
                root.after(0, set_step, '完成')
                nxt.config(text='完成', state='normal', command=root.destroy)
            except Exception as e:
                root.after(0, messagebox.showerror, APP_NAME, f'安装失败：{e}')
                root.after(0, set_step, '失败')
        threading.Thread(target=worker, daemon=True).start()
    def go_next():
        if pages_key[0] == 'welcome':
            pages_key[0] = 'path'
            show('path')
            back.config(state='normal')
            refresh_preview()
        elif pages_key[0] == 'path':
            okv, p, err = validate_target(var_target.get())
            if not okv:
                messagebox.showwarning(APP_NAME, err)
                return
            state['target'] = p
            pages_key[0] = 'install'
            show('install')
            back.config(state='disabled')
            nxt.config(state='disabled')
            do_install()
    def go_back():
        if pages_key[0] == 'path':
            pages_key[0] = 'welcome'
            show('welcome')
            back.config(state='disabled')
    pages_key = ['welcome']
    nxt.config(command=go_next)
    back.config(command=go_back)
    show('welcome')

    def on_close():
        if state['done'] and var_launch.get():
            exe = os.path.join(state['target'], EXE_NAME)
            if os.path.isfile(exe):
                try:
                    os.startfile(exe)
                except OSError:
                    pass
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', on_close)
    root.mainloop()
def main(argv=None):
    argv = [a for a in (sys.argv[1:] if argv is None else argv)]
    if argv and argv[0].upper() == '/S':
        sys.exit(do_silent(os.path.abspath(argv[1]) if len(argv) > 1 else default_target()))
    if argv and argv[0].upper() == '/U':
        ok = do_uninstall(resolve_uninstall_target(argv[1] if len(argv) > 1 else None))
        _logfile()
        sys.exit(0 if ok else 2)
    run_gui()
if __name__ == '__main__':
    main()
