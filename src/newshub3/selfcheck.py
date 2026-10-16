"""selfcheck.py —— 自检通道 + 本地注册自愈（路径无关的核心）。\n\n设计目标：软件目录被移动/复制到任何路径、任何设备，双击运行即恢复可用：\n1. doctor()：一套离线/在线自检项，产出结构化结果（仪表盘「自检」页与\n   安装器装后自检共用同一实现）；\n2. ensure_local_registration()：自愈注册——开机自启注册表、开始菜单/桌面\n   快捷方式若缺失或指向旧路径，自动改写到当前 exe 路径；\n3. 所有注册只写 HKCU（无需管理员），所有路径运行时推导，不在任何\n   配置里保存绝对自身路径（移植后无残留引用）。\n"""
import ctypes
import os
import sys
LOG = []
def _note(msg):
    LOG.append(str(msg))
def exe_path():
    """当前主程序路径（源码运行时取 sys.argv[0] 对应的包上层不可靠，取 cwd 兜底）。"""
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    else:
        if sys.argv:
            return os.path.abspath(sys.argv[0])
        else:
            return os.path.abspath('newshub3')
def app_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _reg_run_value(name='NewsHub'):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run') as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v)
    except OSError:
        return ''
def _set_reg_run(name, quoted_exe):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run') as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, quoted_exe)
def _del_reg_run(name):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass
def register_autostart(exe=None):
    exe = exe or exe_path()
    _set_reg_run('NewsHub', f'"{exe}"')
    return f'"{exe}"'
def unregister_autostart():
    _del_reg_run('NewsHub')
def _shortcut_paths(exe=None):
    """开始菜单 + 桌面快捷方式路径（与本机用户绑定，随时可重建）。"""
    home = os.path.expanduser('~')
    return [os.path.join(home, 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'NewsHub.lnk'), os.path.join(home, 'Desktop', 'NewsHub.lnk')]
def _make_shortcut(lnk, exe):
    ps = f"$ws = New-Object -ComObject WScript.Shell;$lk = $ws.CreateShortcut('{lnk}');$lk.TargetPath = '{exe}';$lk.WorkingDirectory = '{os.path.dirname(exe)}';$lk.IconLocation = '{exe},0';$lk.Save()"
    import subprocess
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, timeout=30, creationflags=134217728)
def _shortcut_target(lnk):
    """读快捷方式目标（用 PowerShell 反查 .lnk；失败返回空）。"""
    try:
        import subprocess
        r = subprocess.run(['powershell', '-NoProfile', '-Command', f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}').TargetPath"], capture_output=True, timeout=30, creationflags=134217728)
        return r.stdout.decode('gbk', 'replace').strip()
    except Exception:
        return ''
def ensure_local_registration(fix=True, want_autostart=True, want_shortcuts=True):
    """自愈入口：核对自启注册与快捷方式是否指向当前路径，偏差即修。

    返回 (ok, report_lines)。ok=False 表示仍有未修复项（fix=False 时只体检）。
    """
    exe = exe_path()
    lines = []
    ok = True
    cur = _reg_run_value()
    if not want_autostart:
        if cur:
            if fix:
                unregister_autostart()
                lines.append(f'自启：已按配置移除（原 {cur}）')
            else:
                lines.append(f'自启：存在 {cur}（未启用自启，建议移除）')
    elif cur == f'"{exe}"':
        lines.append('自启注册：✅ 指向当前路径')
    elif cur:
        if fix:
            register_autostart(exe)
            lines.append(f'自启注册：♻️ 已从旧路径改写\n  旧：{cur}\n  新："{exe}"')
        else:
            ok = False
            lines.append(f'自启注册：⚠️ 指向旧路径 {cur}（当前 {exe}）')
    else:
        if fix:
            register_autostart(exe)
            lines.append(f'自启注册：➕ 已创建（"{exe}"）')
        else:
            ok = False
            lines.append('自启注册：⚠️ 未注册')
    for lnk in _shortcut_paths(exe):
        name = '开始菜单' if 'Start Menu' in lnk else '桌面'
        if not want_shortcuts:
            continue
        if os.path.exists(lnk):
            tgt = _shortcut_target(lnk)
            if os.path.normcase(tgt) == os.path.normcase(exe):
                lines.append(f'{name}快捷方式：✅')
            elif fix:
                _make_shortcut(lnk, exe)
                lines.append(f'{name}快捷方式：♻️ 已改写（原 {tgt or "?"}）')
            else:
                ok = False
                lines.append(f'{name}快捷方式：⚠️ 指向 {tgt or "?"}（当前 {exe}）')
        elif fix:
            try:
                _make_shortcut(lnk, exe)
                lines.append(f'{name}快捷方式：➕ 已创建')
            except Exception as e:
                ok = False
                lines.append(f'{name}快捷方式：⚠️ 创建失败 {e}')
        else:
            ok = False
            lines.append(f'{name}快捷方式：⚠️ 不存在')
    return (ok, lines)
def _check(label, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        return {'item': label, 'ok': False, 'detail': str(e)[:120]}
    return {'item': label, 'ok': bool(ok), 'detail': str(detail)}
def doctor(app, quick=False, smtp=False):
    """自检通道主入口。返回 {"ok":..., "items":[...], "report":...}。

    quick=True 跳过网络与来源探测（离线装机也能出报告）；
    smtp=True 额外做一次真实 SMTP 登录握手（不发信）。
    """
    from .config import Config
    items = []
    cfg_path = getattr(app.cfg, 'path', None) or os.path.join(app_root(), 'config.json')
    data_dir = getattr(app, 'data_dir', None) or os.path.join(app_root(), 'data')
    items.append(_check('配置文件', lambda : (os.path.isfile(cfg_path), cfg_path if os.path.isfile(cfg_path) else 'config.json 缺失')))
    def _cfg_load():
        cfg = app.cfg
        cfg.reload(force=True)
        n = len(cfg.sources)
        return (True, f"JSON 合法；启用来源 {n} 个；引导{'已完成' if cfg.onboarded else '未完成'}")
    items.append(_check('配置解析', _cfg_load))
    def _data_writable():
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, '.write_test')
        with open(probe, 'w') as f:
            f.write('ok')
        os.remove(probe)
        return (True, data_dir)
    items.append(_check('数据目录可写', _data_writable))
    def _db():
        n = app.db.count()
        return (n >= 0, f'news.db 可用；库内 {n} 条')
    items.append(_check('数据库', _db))
    def _port():
        cfg = app.cfg
        import socket
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', cfg.dashboard_port))
                return (True, f'端口 {cfg.dashboard_port} 可用')
            except OSError:
                in_use = False
                try:
                    s2 = socket.create_connection(('127.0.0.1', cfg.dashboard_port), 2)
                    s2.close()
                    in_use = True
                except OSError:
                    pass
                return (in_use, f'端口被占用（{"程序已在运行=正常" if in_use else "未知进程占用"}）')
    items.append(_check('仪表盘端口', _port))
    reg_ok, reg_lines = ensure_local_registration(fix=False)
    items.append({'item': '本地注册（自启/快捷方式）', 'ok': reg_ok, 'detail': '；'.join(reg_lines) if reg_lines else '无'})
    if not quick:
        def _net():
            from .core import probe_network
            return (probe_network(), '外网探测通过' if probe_network() else '离线（可稍后自动恢复）')
        items.append(_check('网络', _net))
        def _src():
            ok_n, total, sample = (0, 0, '')
            for s in app.cfg.sources[:4]:
                total += 1
                try:
                    from .collectors.base import fetch
                    r = fetch(s['url'], timeout=8, retries=0)
                    ok_n += 1
                    if not sample:
                        sample = f"首个成功源 {s['name']}"
                except Exception:
                    continue
            return (ok_n > 0, f'{ok_n}/{total} 抽检可达。{sample}')
        items.append(_check('信息源抽检', _src))
    if smtp and app.cfg.channel_ready():
        def _smtp():
            from .push.smtp_channel import verify_smtp
            s = app.cfg.smtp
            ok, err = verify_smtp(s['服务器'], s['端口'], s['账号'], s['授权码'], s['收件人'], send_test=False)
            return (ok, 'SMTP 登录握手成功') if ok else (ok, err)
        items.append(_check('SMTP 握手', _smtp))
    elif smtp:
        items.append({'item': 'SMTP 握手', 'ok': False, 'detail': '通道凭证未填写'})
    ok_all = all((i['ok'] for i in items))
    report = '\n'.join((f"{'✅' if i['ok'] else '⚠️'} {i['item']}: {i['detail']}" for i in items))
    try:
        os.makedirs(os.path.join(data_dir, 'logs'), exist_ok=True)
        with open(os.path.join(data_dir, 'logs', 'selfcheck.txt'), 'w', encoding='utf-8') as f:
            f.write(report + '\n')
    except Exception:
        pass
    return {'ok': ok_all, 'items': items, 'report': report}
def repair_registration():
    return ensure_local_registration()
def messagebox_info(msg, title='NewsHub 自检'):
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, str(msg), title, 0)
