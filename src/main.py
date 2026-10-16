"""main.py —— NewsHub 入口。\n\n用法（在 NewsHub 目录下）：\n  python -m newshub3.main              # 常驻运行：心跳定时 + 本地仪表盘 http://127.0.0.1:8365\n  python -m newshub3.main --collect    # 手动采集一轮后退出（不推送）\n  python -m newshub3.main --preview    # 在控制台打印当前窗口简讯预览后退出\n  python -m newshub3.main --test-push  # 向已配置通道发送一条测试简讯后退出\n  python -m newshub3.main --doctor     # 自检通道：体检并打印报告（--smtp 加握手, --fix 顺带修复注册）\n  python -m newshub3.main --port 8365  # 覆盖仪表盘端口\n"""
import argparse
import os
import sys
import threading
import time
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from newshub3.core import NewsHubApp
    from newshub3.dashboard import make_server, write_static_dashboard
    from newshub3.logutil import setup_logging
    from newshub3.scheduler import Heartbeat
else:
    from .core import NewsHubApp
    from .dashboard import make_server, write_static_dashboard
    from .logutil import setup_logging
    from .scheduler import Heartbeat
def app_root():
    """安装路径：exe 冻结运行时取 exe 所在目录；源码运行取包上层目录。\n\n    config.json 与 data/（含 news.db、digests/ 归档）始终存放在安装路径下。\n    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = app_root()
CONFIG_PATH = os.path.join(ROOT, 'config.json')
DATA_DIR = os.path.join(ROOT, 'data')
def _alert(msg):
    """打印提示；若运行在无控制台环境（stdout 不可用）则弹窗。"""
    _say(msg)
    if sys.stdout is None:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, 'NewsHub', 48)
        except Exception:
            return None
def _say(msg):
    """控制台可用才打印（windowed 构建无控制台，print 会异常/不可见）。"""
    try:
        if sys.stdout is not None:
            print(msg)
    except Exception:
        return None
def _say_or_box(msg, title='NewsHub'):
    """单次命令的收尾输出：有控制台打印，无控制台弹窗摘要（报告已落盘）。"""
    if sys.stdout is not None:
        print(msg)
        return
    else:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, title, 64)
        except Exception:
            return None
def _build_app(port_override=None):
    app = NewsHubApp(CONFIG_PATH, DATA_DIR)
    if port_override:
        app.cfg._cfg.setdefault('仪表盘', {})['端口'] = port_override
    return app
def main():
    parser = argparse.ArgumentParser(description='NewsHub 分类资讯采集汇总器')
    parser.add_argument('--collect', action='store_true', help='采集一轮后退出')
    parser.add_argument('--preview', action='store_true', help='打印简讯预览后退出')
    parser.add_argument('--test-push', action='store_true', help='发送测试简讯后退出')
    parser.add_argument('--doctor', action='store_true', help='自检：体检并打印报告后退出')
    parser.add_argument('--doctor-quick', action='store_true', help='自检跳过网络/来源探测（离线可用）')
    parser.add_argument('--smtp', action='store_true', help='自检附带 SMTP 登录握手')
    parser.add_argument('--fix', action='store_true', help='自检时顺带修复本地注册（自启/快捷方式）')
    parser.add_argument('--port', type=int, default=None, help='仪表盘端口覆盖')
    parser.add_argument('--verbose', action='store_true', help='调试日志')
    parser.add_argument('--version', action='store_true', help='版本号')
    args = parser.parse_args()
    if args.version:
        if __package__ in (None, ''):
            from newshub3 import __version__
        else:
            from . import __version__
        _say_or_box(f'NewsHub v{__version__}')
        return
    setup_logging(DATA_DIR, verbose=args.verbose)
    import logging
    logging.getLogger('newshub3.main')
    try:
        app = _build_app(args.port)
    except Exception as e:
        tpl = os.path.join(ROOT, 'config.template.json')
        if '不存在' in str(e) and os.path.isfile(tpl):
            try:
                import shutil as _sh
                _sh.copy2(tpl, CONFIG_PATH)
                app = _build_app(args.port)
                _say('[NewsHub] config.json 缺失，已从自带模板初始化。')
            except Exception as e2:
                _alert(f'[NewsHub] 模板初始化失败：{e2}')
                sys.exit(1)
        else:
            _alert(f'[NewsHub] 启动失败：{e}\n请检查 NewsHub 目录下的 config.json 是否存在且为合法 JSON。')
            sys.exit(1)
    if args.doctor or args.doctor_quick:
        from newshub3.selfcheck import doctor, repair_registration
        if args.fix:
            ok_reg, lines = repair_registration()
            _say('== 本地注册修复 ==')
            for ln in lines:
                _say('  ' + ln)
        result = doctor(app, quick=args.doctor_quick, smtp=args.smtp)
        _say('== NewsHub 自检报告 ==')
        _say(result['report'])
        _say_or_box(f"结论：{'✅ 全部通过' if result['ok'] else '⚠️ 存在需关注项'}\n完整报告已存 data/logs/selfcheck.txt")
        sys.exit(0 if result['ok'] else 1)
    if args.collect:
        stats = app.run_collection()
        summary = '\n'.join(f"  {'✅' if s['ok'] else '❌'} {name}: {'新增 ' + str(s['count']) + ' 条' if s['ok'] else s['error']}" for name, s in stats.items())
        write_static_dashboard(app)
        _say(summary)
        _say_or_box(f'采集完成。库内共 {app.db.count()} 条。\n{summary[:800]}')
        return
    if args.test_push:
        ok, err = app.send_test_push()
        _say_or_box('✅ 测试简讯已发送，请查收手机。' if ok else f'❌ 发送失败：{err}')
        sys.exit(0 if ok else 2)
    if args.preview:
        for title, body in app.preview_messages():
            _say(f'\n===== {title} =====\n{body}\n')
        return
    from newshub3 import __version__
    cfg = app.cfg
    _say('========================================================')
    _say(f'  NewsHub v{__version__}  常驻运行中')
    _say(f'  仪表盘:  http://127.0.0.1:{cfg.dashboard_port}/')
    _say('  推送通道: ' + f'{cfg.channel_type}' + ('（凭证未填→发送时会失败并记录，填好自动生效）' if not cfg.channel_ready() else ''))
    _say('  推送时刻: ' + ' / '.join((t.strftime('%H:%M') for t in cfg.push_times)) + '（改 config.json 后 1 分钟内生效）')
    _say('  日志: data/logs/newshub3.log')
    _say('========================================================')
    server = None
    try:
        try:
            server = make_server(app)
        except OSError as e:
            _alert(f'[NewsHub] 端口 {cfg.dashboard_port} 被占用：程序可能已在运行，本次退出。\n（{e}）\n如需双开，请改 config.json 的 仪表盘.端口。')
        write_static_dashboard(app)
        if cfg.onboarded:
            try:
                from newshub3.selfcheck import ensure_local_registration
                reg_ok, reg_lines = ensure_local_registration(fix=True)
                if not reg_ok:
                    _say('[提示] 本地注册自愈存在未完成项，详见自检页。')
                for _ln in reg_lines:
                    if '♻️' in _ln or '➕' in _ln:
                        _say('  ' + _ln.replace('\n', ' '))
            except Exception:
                pass
        hb = Heartbeat(app)
        hb.start()
        url = f'http://127.0.0.1:{cfg.dashboard_port}/'
        if cfg.ui_mode == 'window':
            _run_windowed(app, url, server)
        else:
            if cfg.auto_open_browser:
                import webbrowser
                webbrowser.open(url)
            _say(f'就绪。浏览器打开 {url} 查看仪表盘。')
            server.serve_forever(poll_interval=0.5)
    finally:
        if server:
            server.shutdown()
    app.db.close()
def _run_windowed(app, url, server):
    """桌面阅读窗口：双击 exe 直接弹窗阅读；关窗即整体退出。

    pywebview 用系统自带 WebView2（Win11 内置）；不可用时回退浏览器模式。
    """
    try:
        import webview
    except ImportError:
        _say('[提示] 未安装 pywebview（pip install pywebview），回退浏览器模式。')
        if app.cfg.auto_open_browser:
            import webbrowser
            webbrowser.open(url)
        server.serve_forever(poll_interval=0.5)
        return
    try:
        webview.create_window('NewsHub · 信息简报', url, width=1200, height=920, min_size=(880, 600))
        threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.5}, daemon=True, name='dashboard-http').start()
        _say(f'桌面阅读窗口已打开（{url}）。关闭窗口即退出 NewsHub。')
        webview.start()
    except Exception as e:
        _alert(f'[NewsHub] 桌面窗口启动失败（{e}），已回退浏览器模式。')
        import webbrowser
        webbrowser.open(url)
        server.serve_forever(poll_interval=0.5)
if __name__ == '__main__':
    main()
