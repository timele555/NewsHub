"""dashboard —— NewsHub 界面层。\n\n- 现代简洁风格（参考 Linear/Vercel/Notion 一类顶级网页设计：浅灰底、白卡片、\n  12px 圆角、细边框、单一强调色、系统字体栈），纯内联 CSS/JS，无外部 CDN；\n- 首次使用自动进入 /setup 新手引导：网络握手 → 选板块 → 绑定QQ邮箱（SMTP握手）\n  → 设定推送时间 → 完成并推送第一期；\n- /settings 设置中心：推送邮箱/时间、板块与关键词、文章API；\n- 本地服务仅绑定 127.0.0.1，接口供阅读窗口与浏览器使用。\n"""
import html as htm
import json
import logging
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote as urlquote
from urllib.parse import urlparse, parse_qs
from .boards import BOARD_PRESETS, SOURCE_REGISTRY, build_sources_config, build_keywords
from .core import Busy, apply_onboarding, probe_network
from .digest import render_entries_html
from .push.smtp_channel import verify_smtp, SmtpChannel
log = logging.getLogger('newshub3.dashboard')
CSS = '\n:root{--bg:#f6f7f9;--card:#ffffff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;\n--accent:#2563eb;--accent-soft:#eff6ff;--ok:#16a34a;--bad:#dc2626;--warn:#d97706;\n--chip:#f1f5f9;--radius:12px;--radius-s:8px}\n*{box-sizing:border-box;margin:0;padding:0}\nhtml{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}\nbody{font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",\"PingFang SC\",\"Microsoft YaHei\",\n\"Helvetica Neue\",Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6;font-size:14px}\na{color:var(--accent);text-decoration:none}\na:hover{text-decoration:underline}\n.nav{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.94);\nbackdrop-filter:blur(10px);border-bottom:1px solid var(--line)}\n.nav-inner{max-width:1080px;margin:0 auto;display:flex;align-items:center;gap:6px;\npadding:0 20px;height:54px}\n.logo{font-weight:700;font-size:16px;letter-spacing:.2px;display:flex;align-items:center;\ngap:8px;margin-right:14px;white-space:nowrap}\n.tab{padding:6px 14px;border-radius:8px;color:var(--muted);font-size:14px;white-space:nowrap}\n.tab:hover{color:var(--ink);background:var(--chip);text-decoration:none}\n.tab.on{color:var(--accent);background:var(--accent-soft);font-weight:600}\n.nav .sp{flex:1}\n.pill{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);\nbackground:var(--chip);padding:4px 12px;border-radius:999px;white-space:nowrap}\n.dot{width:7px;height:7px;border-radius:50%;background:var(--bad)}\n.dot.on{background:var(--ok)}\n.wrap{max-width:1080px;margin:0 auto;padding:22px 20px 90px}\n.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);\npadding:18px 20px;margin-bottom:14px}\n.card h2{font-size:15px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}\n.card h2 .hint{font-size:12px;color:var(--muted);font-weight:400;margin-left:auto}\n.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}\n.chip{padding:5px 13px;border:1px solid var(--line);border-radius:999px;font-size:13px;\ncolor:var(--muted);cursor:pointer;background:var(--card)}\n.chip:hover{color:var(--ink);text-decoration:none}\n.chip.on{background:var(--ink);border-color:var(--ink);color:#fff}\n.toolbar select,.toolbar input{font:inherit;font-size:13px;padding:6px 10px;\nborder:1px solid var(--line);border-radius:var(--radius-s);background:var(--card);color:var(--ink)}\n.toolbar input{width:200px}\n.toolbar .sp{flex:1}\n.btn{font:inherit;font-size:13px;font-weight:600;padding:7px 16px;border:1px solid var(--line);\nborder-radius:var(--radius-s);background:var(--card);cursor:pointer;color:var(--ink);white-space:nowrap}\n.btn:hover{border-color:#cbd5e1;background:var(--chip)}\n.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}\n.btn.primary:hover{background:#1d4ed8}\n.meta{color:var(--muted);font-size:12px;margin:8px 0 14px}\n.wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}\n.tile{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);\npadding:14px 16px;display:flex;flex-direction:column;justify-content:space-between;\ntransition:border-color .15s}\n.tile:hover{border-color:var(--accent)}\n.tile .t a{color:var(--ink);font-size:14px;font-weight:600;line-height:1.55}\n.tile .t a:hover{color:var(--accent)}\n.tile .m{margin-top:10px;font-size:12px;color:var(--muted);display:flex;gap:6px;\nalign-items:center;flex-wrap:wrap}\n.badge{display:inline-block;padding:1px 9px;border-radius:999px;background:var(--chip);\ncolor:var(--muted);font-size:11px}\n.badge.notice{background:#fef3c7;color:var(--warn)}\n.badge.pushed{background:#dcfce7;color:var(--ok)}\n.badge.archived{background:var(--chip);color:var(--muted)}\n.item{padding:12px 2px;border-bottom:1px solid var(--line)}\n.item:last-child{border-bottom:none}\n.item .t a{color:var(--ink);font-size:14px;font-weight:600}\n.item .t a:hover{color:var(--accent)}\n.item .sum{color:var(--muted);font-size:13px;margin-top:2px}\n.item .meta2{font-size:12px;color:var(--muted);margin-top:3px;display:flex;gap:8px;align-items:center}\ntable{width:100%;border-collapse:collapse;font-size:13px}\ntd,th{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;color:var(--muted)}\nth{color:var(--ink);font-weight:600;background:var(--chip)}\nth:first-child{border-radius:var(--radius-s) 0 0 var(--radius-s)}\nth:last-child{border-radius:0 var(--radius-s) var(--radius-s) 0}\n.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}\n.notice-line{font-size:13px;color:var(--warn);background:#fffbeb;border:1px solid #fde68a;\npadding:9px 13px;border-radius:var(--radius-s);margin:8px 0}\n.empty{color:var(--muted);text-align:center;padding:40px 0}\n.hint{font-size:12px;color:var(--muted);background:var(--chip);padding:10px 14px;\nborder-radius:var(--radius-s);margin-top:16px;line-height:1.7}\ncode{background:var(--chip);padding:1px 6px;border-radius:5px;font-size:12px}\n.calwrap summary{cursor:pointer;font-size:14px;font-weight:700;user-select:none}\n.cal{border-collapse:collapse;margin:12px auto 4px}\n.cal th{background:none;border:none;font-size:11px;color:var(--muted);padding:2px 0;\ntext-align:center;width:46px;font-weight:600}\n.cal td{border:none;text-align:center;padding:3px 0;width:46px}\n.cal .dn{color:var(--muted);text-decoration:none;padding:3px 8px;border-radius:8px;\ndisplay:inline-block}\n.cal a.dn:hover{background:var(--accent-soft);color:var(--accent)}\n.cal .has-arts .dn{color:var(--ink);font-weight:700;background:var(--chip)}\n.cal .has-digest .dn{color:#fff;font-weight:700;background:var(--accent)}\n.cal .today .dn{box-shadow:0 0 0 1.5px var(--accent)}\n.cal .other .dn{color:#cbd5e1}\n.cal-head{text-align:center;font-size:13px;margin-top:8px}\n.cal-head b{margin:0 14px}\n.cal-head a{margin:0 8px}\n.steps{display:flex;gap:6px;margin-bottom:18px}\n.step-dot{flex:1;height:4px;border-radius:999px;background:var(--line)}\n.step-dot.on{background:var(--accent)}\n.wstep{display:none}\n.wstep.on{display:block}\n.wstep h1{font-size:22px;font-weight:700;margin-bottom:4px}\n.wstep .sub{color:var(--muted);font-size:13px;margin-bottom:18px}\n.boards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}\n.bcard{border:1.5px solid var(--line);border-radius:var(--radius);padding:14px 16px;\ncursor:pointer;background:var(--card);transition:all .15s}\n.bcard.on{border-color:var(--accent);background:var(--accent-soft)}\n.bcard .bt{font-weight:700;font-size:14px;display:flex;gap:8px;align-items:center}\n.bcard .bt .tick{margin-left:auto;color:var(--accent);opacity:0;font-weight:700}\n.bcard.on .tick{opacity:1}\n.bcard .bd{font-size:12px;color:var(--muted);margin-top:4px}\n.field{margin-bottom:12px}\n.field label{display:block;font-size:12px;font-weight:600;color:var(--muted);margin-bottom:5px}\n.field input:not([type=checkbox]),.field textarea{font:inherit;font-size:13px;width:100%;\npadding:8px 11px;border:1px solid var(--line);border-radius:var(--radius-s);\ncolor:var(--ink);background:var(--card)}\n.field input[type=checkbox]{width:16px;height:16px;vertical-align:-2px}\n.field input:focus,.field textarea:focus{outline:none;border-color:var(--accent)}\n.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}\n.wfoot{display:flex;gap:8px;margin-top:20px;align-items:center}\n.result{font-size:13px;margin-left:10px}\n.result.ok{color:var(--ok)}.result.bad{color:var(--bad)}\n.success-hero{text-align:center;padding:50px 20px}\n.success-hero .big{font-size:44px}\n.success-hero h1{font-size:20px;font-weight:700;margin:12px 0 6px}\n.success-hero p{color:var(--muted);font-size:13px}\n#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--ink);\ncolor:#fff;padding:10px 20px;border-radius:10px;font-size:13px;opacity:0;transition:.3s;\npointer-events:none;z-index:99}\n#toast.show{opacity:.94}\n@media (max-width:760px){.grid2{grid-template-columns:1fr}.nav .tab{padding:6px 9px}}\n.chat{display:flex;flex-direction:column;gap:10px;min-height:320px;max-height:56vh;\noverflow-y:auto;padding:4px 2px}\n.msg{max-width:86%;padding:10px 14px;border-radius:12px;font-size:13px;\nwhite-space:pre-wrap;word-break:break-word;line-height:1.7}\n.msg.user{align-self:flex-end;background:var(--accent);color:#fff;\nborder-bottom-right-radius:4px}\n.msg.bot{align-self:flex-start;background:var(--chip);color:var(--ink);\nborder-bottom-left-radius:4px}\n.msg.bot b{color:var(--accent)}\n.chatbar{display:flex;gap:8px;margin-top:14px}\n.chatbar input{flex:1;font:inherit;font-size:13px;padding:10px 13px;\nborder:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink)}\n.chatbar input:focus{outline:none;border-color:var(--accent)}\n.chatbar .btn{border-radius:10px}\n.sugg{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}\n.sugg .chip{font-size:12px}\n.sc-item{display:flex;gap:10px;align-items:flex-start;padding:10px 4px;\nborder-bottom:1px solid var(--line);font-size:13px}\n.sc-item:last-child{border-bottom:none}\n.sc-item .st{font-size:16px;line-height:1.3}\n.sc-item .bd{flex:1}\n.sc-item .bd b{display:block;font-size:13px}\n.sc-item .bd span{color:var(--muted);font-size:12px;word-break:break-all}\n'
def _nav(cfg, active, net_ok=True):
    parts = ['<div class="nav"><div class="nav-inner"><a class="logo" href="/">📰 NewsHub</a>']

    def tab(href, label, key):
        cls = 'tab on' if active == key else 'tab'
        parts.append(f'<a class="{cls}" href="{href}">{label}</a>')
    tab('/', '首页', 'home')
    tab('/digest', '今日简讯', 'digest')
    if cfg.onboarded:
        tab('/agent', '🤖 Agent', 'agent')
        tab('/selfcheck', '自检', 'selfcheck')
        tab('/settings', '设置', 'settings')
    parts.append('<span class="sp"></span>')
    state = '推送通道就绪' if net_ok else '通道未配置'
    parts.append(f'<span class="pill"><span class="dot{" on" if net_ok else ""}"></span>{state}</span>')
    parts.append('</div></div>')
    return ''.join(parts)
def _calendar_html(db, month=None):
    """月历：蓝底=有存档简讯（📰回看），灰底加粗=有资讯。"""
    import calendar as _cal
    from datetime import date as _date, timedelta
    today = _date.today()
    first = today.replace(day=1)
    if month:
        try:
            y, m = (int(x) for x in month.split('-'))
            if 2000 <= y <= 2100 and 1 <= m <= 12:
                first = _date(y, m, 1)
        except (ValueError, TypeError):
            pass
    digests = db.digest_dates()
    arts = db.article_date_counts()
    prev_m = (first - timedelta(days=1)).strftime('%Y-%m')
    next_m = _date(first.year + (first.month == 12), first.month % 12 + 1, 1).strftime('%Y-%m')
    today_s = today.strftime('%Y-%m-%d')
    weeks = _cal.Calendar(firstweekday=0).monthdayscalendar(first.year, first.month)
    grid_start = first - timedelta(days=first.weekday())
    rows = []
    for w_idx, week in enumerate(weeks):
        cells = []
        for d_idx, dnum in enumerate(week):
            real = grid_start + timedelta(days=w_idx * 7 + d_idx)
            ds = real.strftime('%Y-%m-%d')
            if real.month != first.month:
                cells.append(f'<td class="other"><span class="dn">{real.day}</span></td>')
                continue
            cls = []
            if ds in digests:
                cls.append('has-digest')
            elif ds in arts:
                cls.append('has-arts')
            if ds == today_s:
                cls.append('today')
            linked = ds in digests or ds in arts
            num = f'<a class="dn" href="/?cat=全部&date={ds}" title="{ds} 的资讯">{real.day}</a>' if linked else f'<span class="dn">{real.day}</span>'
            dg = f'<a class="dgi" title="{ds} 简讯存档" href="/digest?date={ds}">📰</a>' if ds in digests else ''
            cells.append(f'<td class="{" ".join(cls)}">{num}{dg}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    head = f'<div class="cal-head"><a href="/?m={prev_m}">‹</a><b>{first.year}年{first.month}月</b><a href="/?m={next_m}">›</a><a href="/">本月</a></div>'
    table = '<table class="cal"><tr>' + ''.join((f'<th>{w}</th>' for w in ('一', '二', '三', '四', '五', '六', '日'))) + '</tr>' + ''.join(rows) + '</table>'
    return head + table
def render_dashboard(app):
    db, cfg = (app.db, app.cfg)

    def render(cat='全部', date='全部', search='', limit=200, month=None, view='grid'):
        all_rows = db.articles_for_dashboard(limit=2000)
        cats = ['全部'] + sorted(({r['category'] for r in all_rows} | {s['分类'] for s in cfg.all_sources() if s.get('分类')}))
        dates = ['全部'] + db.dashboard_dates()
        rows = db.articles_for_dashboard(cat, date, search or None, limit)
        health = {r['source']: r for r in db.source_health_all()}
        pushes = db.recent_pushes(8)
        cal = _calendar_html(db, month)
        from .pipeline import score_item
        wall = db.articles_for_dashboard(cat, date, search or None, max(60, cfg.wall_limit * 4))
        for r in wall:
            score_item(r, cfg)
        wall.sort(key=lambda r: (r['_score'], r.get('published_at') or r.get('collected_at') or ''), reverse=True)
        wall = wall[:cfg.wall_limit]
        cards = []
        for r in wall:
            pub = (r.get('published_at') or r.get('collected_at') or '')[:16]
            badges = f'<span class="badge">{htm.escape(r["source"])}</span>'
            if r.get('is_notice'):
                badges += '<span class="badge notice">付费·仅提示</span>'
            cards.append(f'<div class="tile"><div class="t"><a href="{htm.escape(r["url"], quote=True)}" target="_blank" rel="noopener">{htm.escape(r["title"])}</a></div><div class="m">{badges}<span>{htm.escape(r["category"])} · {htm.escape(pub)}</span></div></div>')
        wall_html = ''.join(cards) or '<p class="empty">暂无条目，点上方「采集」。</p>'
        rows_html = []
        for r in rows:
            pub = (r.get('published_at') or r.get('collected_at') or '')[:16]
            badges = f'<span class="badge">{htm.escape(r["source"])}</span>'
            if r.get('is_notice'):
                badges += '<span class="badge notice">付费·仅提示</span>'
            if r.get('pushed_push_id'):
                badges += '<span class="badge pushed">已推送</span>'
            if r.get('is_archived'):
                badges += '<span class="badge archived">已归档</span>'
            sum_html = f'<div class="sum">{htm.escape(r["summary"])}</div>' if r.get('summary') else ''
            rows_html.append(f'<div class="item"><div class="t">{badges}<a href="{htm.escape(r["url"], quote=True)}" target="_blank" rel="noopener">{htm.escape(r["title"])}</a></div>{sum_html}<div class="meta2">{htm.escape(r["category"])} · {htm.escape(pub)}</div></div>')
        if not rows_html:
            rows_html.append('<p class="empty">当前筛选下暂无条目。</p>')
        health_rows = ''.join((f'<tr><td>{htm.escape(r["source"])}</td><td class="{"ok" if r["last_ok"] else "bad"}">{"正常" if r["last_ok"] else "失败"}</td><td>{r["last_count"] or 0}</td><td>{htm.escape(r["last_error"] or "")[:60]}</td><td>{htm.escape(r["last_ok"] or r["last_fail"] or "")[:16]}</td></tr>' for r in sorted(health.values(), key=lambda x: x['source'])))
        health_rows = health_rows or '<tr><td colspan="5">尚未采集。</td></tr>'
        push_rows = ''.join((f'<tr><td>{p["pushed_at"][:16]}</td><td>{htm.escape(p["kind"])}</td><td class="{"ok" if p["status"] in ("success", "sent") else "bad"}">{p["status"]}</td><td>{p["entry_count"]}</td><td>{htm.escape(p["channel"] or "")}</td></tr>' for p in pushes))
        push_rows = push_rows or '<tr><td colspan="5">尚无推送记录。</td></tr>'
        view_links = f'<a class="chip{" on" if view == "grid" else ""}" href="/?cat={urlquote(cat)}&date={urlquote(date)}&view=grid">▦ 标题墙</a><a class="chip{" on" if view == "list" else ""}" href="/?cat={urlquote(cat)}&date={urlquote(date)}&view=list">≡ 列表</a>'
        date_opts = ''.join((f'<option{" selected" if d == date else ""}>{htm.escape(d)}</option>' for d in dates))
        chips = ' '.join((f'<a class="chip{" on" if c == cat else ""}" href="/?cat={urlquote(c)}&date={urlquote(date)}&view={urlquote(view)}">{htm.escape(c)}</a>' for c in cats if c))
        api_state = '文章API 已启用' if cfg.article_api_enabled else '文章API 未启用（设置页可接入）'
        net_on = 'on' if cfg.channel_ready() else ''
        body_html = ('<div class="wall">' + wall_html + '</div>') if view == 'grid' else ('<div class="card">' + ''.join(rows_html) + '</div>')
        return ''.join(['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>NewsHub · 信息简报</title>\n<link rel="icon" href="/favicon.svg">\n<style>', f'{CSS}', '</style></head><body>\n', _nav(cfg, 'home', net_ok=bool(net_on)), '\n<div class="wrap">\n<div class="toolbar">\n', f'{view_links}', f'{chips}', '\n<span class="sp"></span>\n<select onchange="location=\'/?cat=', f'{urlquote(cat)}', "&date='+this.value+'&view=", f'{urlquote(view)}', '\'">', f'{date_opts}', '</select>\n<input placeholder="搜索标题 / 来源…" value="', f'{htm.escape(search)}', '"\n onkeydown="if(event.key===\'Enter\')location=\'/?cat=', f'{urlquote(cat)}', '&date=', f'{urlquote(date)}', '&view=', f'{urlquote(view)}', '&q=\'+encodeURIComponent(this.value)">\n<button class="btn primary" onclick="act(\'/api/collect\',\'采集中…\')">⟳ 采集</button>\n<button class="btn" onclick="location=\'/digest\'">今日简讯</button>\n<button class="btn" onclick="if(confirm(\'将向绑定邮箱发送一封测试简讯，确定？\'))act(\'/api/test-push\',\'发送中…\')">测试推送</button>\n</div>\n        <div class="meta">标题墙每日精选 ', f'{cfg.wall_limit}', ' 条（来源权重 × 新鲜度）；点击标题打开原文；页面每 5 分钟自动刷新。当前：', f'{htm.escape(api_state)}', '</div>\n<div class="card" id="dz" style="border-style:dashed;text-align:center;padding:22px;cursor:pointer"\n     ondragover="event.preventDefault();this.style.borderColor=\'var(--accent)\';this.style.background=\'var(--accent-soft)\'"\n     ondragleave="this.style.borderColor=\'\';this.style.background=\'\'"\n     ondrop="dropFiles(event)">\n<h2 style="justify-content:center">📤 快捷直发<span class="hint">拖拽文件到此处 → 直接发到绑定邮箱</span></h2>\n<div style="color:var(--muted);font-size:13px">也支持点击选择文件 · 单个 ≤15MB · 单次最多 5 个</div>\n<input type="file" id="dz_input" multiple style="display:none" onchange="sendFiles(this.files)">\n</div>\n<div class="card"><h2>📅 日历<span class="hint">📰 = 有简讯存档 · 加粗 = 当天有资讯</span></h2>', f'{cal}', '</div>\n', f'{body_html}', '\n<div class="card"><h2>来源健康</h2><table><tr><th>来源</th><th>状态</th><th>新增</th><th>最近错误</th><th>时间</th></tr>', f'{health_rows}', '</table></div>\n<div class="card"><h2>推送记录</h2><table><tr><th>时间</th><th>类型</th><th>状态</th><th>条数</th><th>通道</th></tr>', f'{push_rows}', '</table></div>\n<div class="hint">', f'{settings_hint(cfg)}', '\u3000静态副本 <code>data/dashboard.html</code>（按钮需经 <code>http://127.0.0.1:', f'{cfg.dashboard_port}', '</code>）。</div>\n</div><div id="toast"></div>\n<script>setTimeout(()=>location.reload(),300000);\nfunction act(u,msg){var t=document.getElementById(\'toast\');t.textContent=msg||\'处理中…\';t.classList.add(\'show\');\nfetch(u,{method:\'POST\'}).then(r=>r.json()).then(d=>{t.textContent=d.message||\'完成\';setTimeout(()=>location.reload(),900)})\n.catch(e=>{t.textContent=\'请求失败（需经 127.0.0.1:', f'{cfg.dashboard_port}', " 打开）';});}\ndocument.getElementById('dz').addEventListener('click',()=>document.getElementById('dz_input').click());\nfunction dropFiles(ev){ev.preventDefault();var dz=document.getElementById('dz');\ndz.style.borderColor='';dz.style.background='';sendFiles(ev.dataTransfer.files);}\nfunction sendFiles(files){\n if(!files||!files.length)return;\n files=[...files].slice(0,5);\n var total=files.reduce((a,f)=>a+f.size,0);\n if(total>15*1024*1024){var tt=document.getElementById('toast');tt.textContent='超过 15MB 上限';tt.classList.add('show');setTimeout(()=>tt.classList.remove('show'),3000);return}\n var t=document.getElementById('toast');t.textContent='发送中（'+files.length+' 个文件，'+Math.round(total/1024)+'KB）…';t.classList.add('show');\n var body={note:'来自 NewsHub 首页拖拽直发。',files:[]},chain=Promise.resolve();\n files.forEach(f=>chain=chain.then(()=>new Promise(res=>{\n   var fr=new FileReader();fr.onload=()=>{body.files.push({name:f.name,data:String(fr.result).split(',')[1]||''});res()};\n   fr.onerror=()=>res();fr.readAsDataURL(f);})));\n chain.then(()=>fetch('/api/quick-send',{method:'POST',headers:{'Content-Type':'application/json'},\n   body:JSON.stringify(body)})\n   .then(r=>r.json()).then(d=>{t.textContent=d.message||'完成';setTimeout(()=>t.classList.remove('show'),3200);})\n   .catch(e=>{t.textContent='发送失败';}));\n}</script>\n</body></html>"])

    def settings_hint(cfg):
        if cfg.channel_ready():
            return '推送通道就绪。'
        return f'推送通道 <b>{htm.escape(cfg.channel_type)}</b> 凭证未填写：请到<a href=\'/settings\'>设置</a>或编辑 <code>config.json</code>。'
    return render

def render_settings(app):
    cfg = app.cfg
    s = cfg.push.get('SMTP', {}) or {}
    kw_now = '\n'.join(cfg.keywords)
    a = cfg.article_api
    enabled_boards = sorted({src.get('分类') for src in cfg.all_sources() if src.get('enabled')})
    board_cards = []
    for b in BOARD_PRESETS:
        on = 'on' if b['name'] in enabled_boards else ''
        board_cards.append(f'<label class="bcard {on}" data-board="{htm.escape(b["name"])}"><span class="bt">{b["icon"]} {htm.escape(b["name"])}<span class="tick">✓</span></span><span class="bd">{htm.escape(b["desc"])}</span></label>')
    times_now = ', '.join((t.strftime('%H:%M') for t in cfg.push_times))
    api_checked = 'checked' if cfg.article_api_enabled else ''
    return ''.join(['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>设置 · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>', CSS, '</style></head><body>\n', _nav(cfg, 'settings', net_ok=cfg.channel_ready()), '\n<div class="wrap">\n<div class="card"><h2>⚙️ 设置中心<span class="hint">保存后约 30 秒内生效，无需重启</span></h2>\n<div class="field"><label>推送时刻（逗号分隔，可多个，如 08:00, 21:30）</label>\n<input id="s_times" value="', htm.escape(times_now), '"></div>\n<div class="grid2">\n<div class="field"><label>SMTP 服务器</label><input id="s_host" value="', htm.escape(str(s.get('服务器', ''))), '"></div>\n<div class="field"><label>端口（465 SSL / 587 STARTTLS）</label><input id="s_port" value="', htm.escape(str(s.get('端口', 465))), '"></div>\n<div class="field"><label>发件账号（QQ 邮箱地址）</label><input id="s_user" value="', htm.escape(str(s.get('账号', ''))), '"></div>\n<div class="field"><label>SMTP 授权码（留空=不修改）</label><input id="s_pass" type="password" placeholder="留空保持不变"></div>\n<div class="field"><label>收件人（多个用英文逗号分隔）</label><input id="s_to" value="', htm.escape(str(s.get('收件人', ''))), '"></div>\n</div>\n<div class="field"><label>内容板块（勾选=启用该板块来源）</label>\n<div class="boards" id="s_boards">', ''.join(board_cards), '</div></div>\n<div class="field"><label>自定义关键词（每行一个，与板块关键词合并）</label>\n<textarea id="s_kw" rows="4">', htm.escape(kw_now), '</textarea></div>\n<h2 style="font-size:14px">🤖 文章API（可选，接入后 Agent 可理解更复杂表述）</h2>\n<div class="field"><label><input type="checkbox" id="s_api_on" ', api_checked, '> 启用（OpenAI 兼容 chat/completions 接口）</label></div>\n<div class="grid2">\n<div class="field"><label>接口地址</label><input id="s_api_url" value="', htm.escape(str(a.get('接口地址', ''))), '"></div>\n<div class="field"><label>模型</label><input id="s_api_model" value="', htm.escape(str(a.get('模型', ''))), '"></div>\n</div>\n<div class="field"><label>API 密钥（留空=不修改）</label><input id="s_api_key" type="password" placeholder="留空保持不变"></div>\n<div class="wfoot"><button class="btn primary" onclick="save()">保存设置</button><span class="result" id="rst"></span></div>\n</div>\n<div class="hint">设置写回 <code>config.json</code>；程序每分钟自动重读。授权码等敏感字段留空表示沿用原值。</div>\n</div>\n<script>\ndocument.querySelectorAll("#s_boards .bcard").forEach(b=>b.onclick=()=>{b.classList.toggle("on");b.querySelector("input")&&(b.classList.contains("on"))});\nfunction save(){\n var boards=[...document.querySelectorAll("#s_boards .bcard.on")].map(b=>b.dataset.board);\n var kw=document.getElementById("s_kw").value.split(/\\n/).map(s=>s.trim()).filter(Boolean);\n var body={推送时刻:document.getElementById("s_times").value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),\n  SMTP:{服务器:v("s_host"),端口:v("s_port"),账号:v("s_user"),收件人:v("s_to"),授权码:v("s_pass")},\n  板块:boards,自定义关键词:kw,\n  文章API:{启用:document.getElementById("s_api_on").checked,接口地址:v("s_api_url"),模型:v("s_api_model"),密钥:v("s_api_key")}};\n fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})\n  .then(r=>r.json()).then(d=>{var r2=document.getElementById("rst");r2.textContent=d.message||"已保存";r2.className="result "+(d.ok?"ok":"bad")});\n}\nfunction v(id){return document.getElementById(id).value.trim()}\n</script>\n</body></html>'])
SETUP_CSS = '\n.setup-body{background:linear-gradient(160deg,#0c1220 0%,#16233f 55%,#1d3a6e 100%);min-height:100vh}\n.setup-wrap{max-width:880px;margin:0 auto;padding:48px 22px 70px}\n.setup-hero{color:#e8eef6;margin-bottom:26px}\n.setup-hero .logo{font-size:26px;font-weight:800;letter-spacing:.5px;display:flex;align-items:center;gap:10px}\n.setup-hero .sub{color:#9fb0c9;font-size:14px;margin-top:6px}\n.setup-hero .skip{float:right;color:#9fb0c9;font-size:13px;padding:8px 16px;border:1px solid rgba(255,255,255,.18);border-radius:999px;background:rgba(255,255,255,.04);margin-top:-6px}\n.setup-hero .skip:hover{color:#fff;border-color:rgba(255,255,255,.4)}\n.setup-card{background:#fff;border-radius:18px;box-shadow:0 24px 70px rgba(0,0,0,.45);padding:34px 36px 30px}\n.setup-steps{display:flex;align-items:center;margin-bottom:26px}\n.sdot{width:34px;height:34px;border-radius:50%;background:#eef2f7;color:#8a99ad;font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:center;flex:none}\n.sdot.on{background:var(--accent);color:#fff;box-shadow:0 6px 16px rgba(37,99,235,.35)}\n.sdot.done{background:#dcfce7;color:#15803d}\n.sline{flex:1;height:2px;background:#e8edf3;margin:0 8px}\n.slabel{color:var(--muted);font-size:12px;font-weight:600;margin-top:6px;text-align:center}\n.wstep h1{font-size:21px;font-weight:800;margin-bottom:4px}\n.wstep .sub{color:var(--muted);font-size:13px;margin-bottom:20px}\n.setup-foot{display:flex;gap:10px;margin-top:24px;align-items:center;justify-content:flex-end;border-top:1px solid var(--line);padding-top:18px}\n.bcard{border:1.5px solid var(--line);border-radius:14px;padding:14px 16px;cursor:pointer;background:#fff;transition:all .15s;display:block}\n.bcard:hover{border-color:#b9c8dd}\n.bcard.on{border-color:var(--accent);background:var(--accent-soft);box-shadow:0 4px 14px rgba(37,99,235,.12)}\n.bcard .bt{font-weight:700;font-size:14px;display:flex;gap:8px;align-items:center}\n.bcard .bt .tick{margin-left:auto;color:var(--accent);opacity:0;font-weight:700;transition:.15s}\n.bcard.on .tick{opacity:1}\n.bcard .bd{font-size:12px;color:var(--muted);margin-top:4px;line-height:1.6}\n.spinner{display:inline-block;width:14px;height:14px;border:2px solid #c7d4e6;border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;vertical-align:-2px;margin-right:6px}\n@keyframes spin{to{transform:rotate(360deg)}}\n.hintnet{display:inline-flex;align-items:center;font-size:13px}\n'

def render_setup(app):
    cfg = app.cfg
    if cfg.onboarded:
        return '<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n<meta http-equiv=\"refresh\" content=\"0;url=/\"><title>NewsHub</title></head>\n<body style=\"font-family:sans-serif;padding:40px\">已完成引导。<a href=\"/\">进入首页</a></body></html>'
    board_cards = []
    for b in BOARD_PRESETS:
        name = htm.escape(b['name'])
        icon = htm.escape(b['icon'])
        desc = htm.escape(b['desc'])
        board_cards.append(f'<div class="bcard" data-board="{name}" onclick="this.classList.toggle(\'on\');updCount()"><div class="bt">{icon} {name}<span class="tick">✓</span></div><div class="bd">{desc}</div></div>')
    labels = ['网络', '板块', '邮箱', '推送']
    steps_html = ''.join((f'<div style="flex:none;text-align:center"><div class="sdot" id="d{i}">{i + 1}</div><div class="slabel">{lb}</div></div>' if i == len(labels) - 1 else f'<div style="flex:none;text-align:center"><div class="sdot" id="d{i}">{i + 1}</div><div class="slabel">{lb}</div></div><div class="sline" id="l{i}"></div>' for i, lb in enumerate(labels)))
    page = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>新手引导 · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>', CSS, SETUP_CSS, '</style></head><body class="setup-body">\n<div class="setup-wrap">\n<div class="setup-hero"><a class="skip" href="javascript:void(0)" onclick="skipSetup()">跳过引导，直接进入 →</a><div class="logo">📰 NewsHub</div><div class="sub">资讯自动采集与简报推送 · 4 步完成配置（随时可在设置页修改）</div></div>\n<div class="setup-card">\n<div class="setup-steps">', steps_html, '</div>\n<div class="wstep on" id="w0"><h1>👋 欢迎使用</h1><p class="sub">先做一次网络握手，确认能访问信息源。</p>\n<div class="hint hintnet" id="netstate"><span class="spinner"></span>正在自动检测网络…</div>\n</div>\n<div class="wstep" id="w1"><h1>选择内容板块</h1><p class="sub">已选 <b id="bn" style="color:var(--accent)">0</b> 个板块 · 决定采集哪些信息源（之后可随时调整）。</p>\n<div class="boards" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr))">', ''.join(board_cards), '</div></div>\n<div class="wstep" id="w2"><h1>绑定 QQ 邮箱</h1><p class="sub">在 QQ 邮箱网页版「设置 → 账户」开启 SMTP 服务并获取授权码。</p>\n<div class="grid2">\n<div class="field"><label>SMTP 服务器</label><input id="m_host" value="smtp.qq.com"></div>\n<div class="field"><label>端口</label><input id="m_port" value="465"></div>\n<div class="field"><label>QQ 邮箱账号</label><input id="m_user" placeholder="xxx@qq.com"></div>\n<div class="field"><label>SMTP 授权码</label><input id="m_pass" type="password" placeholder="16 位字母授权码"></div>\n<div class="field"><label>收件人（默认自己）</label><input id="m_to" placeholder="xxx@qq.com"></div>\n</div>\n<div class="hintnet" id="rst2" style="font-size:13px;color:var(--muted)"></div>\n<div style="margin-top:14px"><button class="btn" onclick="smtpTest()">先测一下握手（可选）</button></div></div>\n<div class="wstep" id="w3"><h1>推送时间</h1><p class="sub">每天在这些时刻把简报发到上面的邮箱。</p>\n<div class="field"><label>推送时刻（逗号分隔，可多个）</label><input id="m_times" value="08:00"></div>\n<div class="hintnet" id="rst3" style="font-size:13px;color:var(--muted)"></div></div>\n<div class="wstep" id="w4"><div class="success-hero"><div class="big">🎉</div><h1>设置完成！</h1><p id="fp_state">第一期简讯生成中，请稍候查收邮箱…</p><p><a href="/">进入首页 →</a></p></div></div>\n<div class="setup-foot" id="foot">\n<button class="btn" id="b_prev" onclick="go(cur-1)">上一步</button>\n<button class="btn primary" id="b_next" onclick="next()">下一步</button>\n</div>\n</div></div>\n<div id="toast"></div>\n<script>\nvar cur=0;\nfunction go(n){if(n<0||n>3)return;cur=n;\n for(var i=0;i<4;i++){document.getElementById("w"+i).classList.toggle("on",i===n);\n  var d=document.getElementById("d"+i);d.classList.toggle("on",i===n);d.classList.toggle("done",i<n);\n  var l=document.getElementById("l"+i);if(l)l.style.background=i<n?"var(--accent)":"#e8edf3";}\n document.getElementById("b_prev").style.visibility=n===0?"hidden":"visible";\n document.getElementById("b_next").textContent=n===3?"完成并推送第一期":"下一步";\n window.scrollTo(0,0);}\nfunction updCount(){document.getElementById("bn").textContent=document.querySelectorAll(".bcard.on").length}\nfunction next(){\n if(cur===1&&!document.querySelectorAll(".bcard.on").length){toast("至少选择一个板块（或右上角跳过引导）");return}\n if(cur===2){if(!v("m_user")||!v("m_pass")||!v("m_to")){toast("账号 / 授权码 / 收件人 必填（或右上角跳过引导）");return}}\n if(cur===3){finish();return}\n go(cur+1);}\nfunction toast(t){var e=document.getElementById("toast");e.textContent=t;e.classList.add("show");setTimeout(function(){e.classList.remove("show")},2600)}\nfunction v(id){return document.getElementById(id).value.trim()}\nnetTest();\nfunction netTest(){fetch("/api/net").then(function(r){return r.json()}).then(function(d){var e=document.getElementById("netstate");if(d.ok){e.innerHTML="✅ 网络正常，可以开始";e.style.color="var(--ok)"}else{e.innerHTML="⚠️ 当前离线：可先完成配置，联网后自动采集";e.style.color="var(--warn)"}}).catch(function(){document.getElementById("netstate").innerHTML="⚠️ 检测失败，可继续"})}\nfunction smtpTest(){var e=document.getElementById("rst2");e.innerHTML="<span class=spinner></span>握手中…";fetch("/api/setup/test-smtp",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({SMTP:{服务器:v("m_host"),端口:v("m_port"),账号:v("m_user"),授权码:v("m_pass"),收件人:v("m_to")}})}).then(function(r){return r.json()}).then(function(d){e.textContent=d.message;e.style.color=d.ok?"var(--ok)":"var(--bad)"})}\nfunction finish(){var b=document.getElementById("b_next");b.disabled=true;b.textContent="保存中…";\n fetch("/api/setup/finish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({板块:Array.prototype.map.call(document.querySelectorAll(".bcard.on"),function(x){return x.dataset.board}),SMTP:{服务器:v("m_host"),端口:v("m_port"),账号:v("m_user"),授权码:v("m_pass"),收件人:v("m_to")},推送时刻:v("m_times").split(/[,，]/).map(function(s){return s.trim()}).filter(Boolean)})}).then(function(r){return r.json()}).then(function(d){if(!d.ok){b.disabled=false;b.textContent="完成并推送第一期";toast(d.message);return}cur=4;\n for(var i=0;i<4;i++)document.getElementById("w"+i).classList.remove("on");\n document.getElementById("w4").classList.add("on");\n document.getElementById("foot").style.display="none";poll()}).catch(function(){b.disabled=false;b.textContent="完成并推送第一期";toast("网络错误，请重试")})}\nfunction poll(){fetch("/api/setup/status").then(function(r){return r.json()}).then(function(d){var st=d.first_push||{};if(st.done){document.getElementById("fp_state").textContent=st.msg+(st.ok?"":"（可到首页手动重推）")}else{document.getElementById("fp_state").textContent=st.msg||"第一期简讯生成中…";setTimeout(poll,2000)}})}\nfunction skipSetup(){if(!confirm("跳过引导：将启用全部板块来源，邮箱稍后可在「设置」页绑定（未绑定时简讯只存档不发送）。确定跳过？"))return;\n fetch("/api/setup/skip",{method:"POST"}).then(function(r){return r.json()}).then(function(d){location.href="/"}).catch(function(){toast("跳过失败，请重试")})}\n</script>\n</body></html>']
    return ''.join(page)
    board_cards = []
    for b in BOARD_PRESETS:
        board_cards.append(f'<label class="bcard" data-board="{htm.escape(b["name"])}" onclick="this.classList.toggle(\'on\');updCount()"><span class="bt">{b["icon"]} {htm.escape(b["name"])}<span class="tick">✓</span></span><span class="bd">{htm.escape(b["desc"])}</span></label>')
    return ''.join(['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>新手引导 · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>', CSS, '\nbody{background:#fff}</style></head><body>\n<div class="wrap" style="max-width:860px">\n<div class="steps"><div class="step-dot on" id="d0"></div><div class="step-dot" id="d1"></div><div class="step-dot" id="d2"></div><div class="step-dot" id="d3"></div></div>\n<div class="wstep on" id="w0"><h1>👋 欢迎使用 NewsHub</h1><p class="sub">资讯自动采集与简报推送。先确认网络可用。</p>\n<div class="wfoot"><button class="btn primary" onclick="netTest()">网络握手测试</button><span class="result" id="rst0"></span></div>\n<div class="wfoot"><button class="btn primary" onclick="go(1)">下一步</button></div></div>\n<div class="wstep" id="w1"><h1>选择内容板块</h1><p class="sub">已选 <b id="bn">0</b> 个板块（可多选，之后随时在设置页调整）。</p>\n<div class="boards">', ''.join(board_cards), '</div>\n<div class="wfoot"><button class="btn" onclick="go(0)">上一步</button><button class="btn primary" onclick="goBoards()">下一步</button><span class="result" id="rst1"></span></div></div>\n<div class="wstep" id="w2"><h1>绑定 QQ 邮箱</h1><p class="sub">在 QQ 邮箱网页版开启 SMTP 服务并获得授权码（设置 → 账户 → POP3/SMTP）。</p>\n<div class="grid2">\n<div class="field"><label>SMTP 服务器</label><input id="m_host" value="smtp.qq.com"></div>\n<div class="field"><label>端口</label><input id="m_port" value="465"></div>\n<div class="field"><label>QQ 邮箱账号</label><input id="m_user" placeholder="xxx@qq.com"></div>\n<div class="field"><label>SMTP 授权码</label><input id="m_pass" type="password"></div>\n<div class="field"><label>收件人（默认填自己）</label><input id="m_to" placeholder="xxx@qq.com"></div>\n</div>\n<div class="wfoot"><button class="btn" onclick="go(1)">上一步</button><button class="btn" onclick="smtpTest()">SMTP 握手测试</button><button class="btn primary" onclick="goSmtp()">下一步</button><span class="result" id="rst2"></span></div></div>\n<div class="wstep" id="w3"><h1>设定推送时间</h1><p class="sub">每天定时推送一封简报到上面的邮箱。</p>\n<div class="field"><label>推送时刻（逗号分隔，可多个）</label><input id="m_times" value="08:00"></div>\n<div class="wfoot"><button class="btn" onclick="go(2)">上一步</button><button class="btn primary" onclick="finish()">完成并推送第一期</button><span class="result" id="rst3"></span></div></div>\n<div class="wstep" id="w4"><div class="success-hero"><div class="big">🎉</div><h1>设置完成！</h1><p id="fp_state">第一期简讯生成中，请稍候查收邮箱…</p><p><a href="/">进入首页 →</a></p></div></div>\n</div>\n<script>\nfunction go(n){for(var i=0;i<4;i++){document.getElementById("w"+i).classList.toggle("on",i===n);document.getElementById("d"+i).classList.toggle("on",i<=n)}window.scrollTo(0,0)}\nfunction updCount(){document.getElementById("bn").textContent=document.querySelectorAll(".bcard.on").length}\nfunction netTest(){fetch("/api/net").then(r=>r.json()).then(d=>{var e=document.getElementById("rst0");e.textContent=d.message;e.className="result "+(d.ok?"ok":"bad")})}\nfunction goBoards(){var n=document.querySelectorAll(".bcard.on").length;if(!n){var e=document.getElementById("rst1");e.textContent="至少选择一个板块";e.className="result bad";return}go(2)}\nfunction smtpTest(){var e=document.getElementById("rst2");e.textContent="握手中…";e.className="result";fetch("/api/setup/test-smtp",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({SMTP:{服务器:v("m_host"),端口:v("m_port"),账号:v("m_user"),授权码:v("m_pass"),收件人:v("m_to")}})}).then(r=>r.json()).then(d=>{e.textContent=d.message;e.className="result "+(d.ok?"ok":"bad")})}\nfunction goSmtp(){if(!v("m_user")||!v("m_pass")||!v("m_to")){var e=document.getElementById("rst2");e.textContent="账号/授权码/收件人必填";e.className="result bad";return}go(3)}\nfunction v(id){return document.getElementById(id).value.trim()}\nfunction finish(){var e=document.getElementById("rst3");e.textContent="保存中…";e.className="result";fetch("/api/setup/finish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({板块:[...document.querySelectorAll(".bcard.on")].map(b=>b.dataset.board),SMTP:{服务器:v("m_host"),端口:v("m_port"),账号:v("m_user"),授权码:v("m_pass"),收件人:v("m_to")},推送时刻:v("m_times").split(/[,，]/).map(s=>s.trim()).filter(Boolean)})}).then(r=>r.json()).then(d=>{if(!d.ok){e.textContent=d.message;e.className="result bad";return}go(4);poll()})}\nfunction poll(){fetch("/api/setup/status").then(r=>r.json()).then(d=>{var st=d.first_push||{};if(st.running||!st.done){document.getElementById("fp_state").textContent=st.msg||"第一期简讯生成中…";setTimeout(poll,2000)}else{var el=document.getElementById("fp_state");el.textContent=st.msg+(st.ok?"":"（可到首页手动重推）")}})}\n</script>\n</body></html>'])
def render_digest_preview(app):
    ws, we = app.current_window()
    sections = app.build_sections()
    from .digest import render_html
    body = render_html(sections, we)
    span = f'{ws.strftime("%m-%d %H:%M")} → {we.strftime("%m-%d %H:%M")}'
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<title>简讯预览 · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>{CSS}</style></head><body>\n{_nav(app.cfg, "digest", net_ok=app.cfg.channel_ready())}\n<div class="wrap"><div class="card"><h2>📰 当前窗口简讯预览<span class="hint">{htm.escape(span)}</span></h2>{body}</div>\n<div class="toolbar"><a class="chip" href="/">← 首页</a><button class="btn primary" onclick="pushNow()">立即推送本窗口</button></div>\n<div class="hint">预览与正式简讯同一套组稿逻辑（评分 → 每类 Top N → 总条数上限）；历史存档见首页日历 📅。</div>\n</div><script>\nfunction pushNow(){{if(!confirm("将把当前窗口简讯推送到绑定邮箱，确定？"))return;fetch("/api/push-now",{{method:"POST"}}).then(r=>r.json()).then(d=>{{alert(d.message);location.reload()}})}}\n</script></body></html>'
def render_digest_archive(app, date):
    import re as _re
    if not _re.fullmatch('\\d{4}-\\d{2}-\\d{2}', date or ''):
        date = ''
    recs = app.db.get_digests(date) if date else []
    blocks = []
    for r in recs:
        status_tag = {'sent': '已推送', 'local': '仅存档未发送', 'failed': '发送失败'}.get(r.get('status'), r.get('status'))
        body = render_entries_html(r.get('entries', []), r.get('stale_line', ''))
        blocks.append(f'<div style="border-top:1px dashed var(--line);padding-top:8px;margin-top:10px"><div class="meta">{htm.escape(r["time"])} · {htm.escape(str(r.get("kind") or ""))} · {htm.escape(status_tag)} · {r.get("entry_count") or 0} 条（存档 #{r["digest_id"]}）</div>{body}</div>')
    inner = '\n'.join(blocks) if recs else '<p class=\'empty\'>该日期没有简讯存档。</p>'
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<title>简讯存档 {htm.escape(date)} · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>{CSS}</style></head><body>\n{_nav(app.cfg, "digest", net_ok=app.cfg.channel_ready())}\n<div class="wrap"><div class="card"><h2>📰 简讯存档<span class="hint">{htm.escape(date or "")}</span></h2>{inner}</div>\n<div class="toolbar"><a class="chip" href="/">← 首页</a><a class="chip" href="/digest">当前窗口预览</a></div>\n<div class="hint">存档同时落库（digests 表）并写为 <code>data/digests/{htm.escape(date)}_*.md</code>；超过归档天数（默认 30）自动瘦身仅留标题与链接。</div>\n</div></body></html>'
FAVICON_SVG = '<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\">\n<rect x=\"1\" y=\"1\" width=\"62\" height=\"62\" rx=\"12\" fill=\"#0c1220\"/>\n<g transform=\"rotate(-5 32 38)\"><rect x=\"12\" y=\"20\" width=\"34\" height=\"36\" rx=\"2.5\" fill=\"#e8eef6\"/>\n<rect x=\"15.5\" y=\"24\" width=\"27\" height=\"7\" rx=\"1.2\" fill=\"#1a2234\"/>\n<rect x=\"15.5\" y=\"35\" width=\"10\" height=\"10\" rx=\"1.2\" fill=\"#78869e\"/>\n<rect x=\"28\" y=\"35\" width=\"14.5\" height=\"2.4\" rx=\"1.2\" fill=\"#78869e\"/>\n<rect x=\"28\" y=\"39.6\" width=\"14.5\" height=\"2.4\" rx=\"1.2\" fill=\"#78869e\"/>\n<rect x=\"28\" y=\"44.2\" width=\"14.5\" height=\"2.4\" rx=\"1.2\" fill=\"#78869e\"/>\n<rect x=\"15.5\" y=\"48.5\" width=\"27\" height=\"2.4\" rx=\"1.2\" fill=\"#78869e\"/>\n<polygon points=\"46,56 40.5,56 46,50.5\" fill=\"#b0bcce\"/></g>\n<polygon points=\"38,26 58,10 49.5,30\" fill=\"#e8eef6\"/>\n<polygon points=\"38,26 49.5,30 46.5,36\" fill=\"#b0bcce\"/>\n<polygon points=\"46.5,36 49.5,30 53,34\" fill=\"#e8eef6\"/></svg>'
def render_selfcheck(app):
    cfg = app.cfg
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>自检 · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>{CSS}</style></head><body>\n{_nav(cfg, "selfcheck", net_ok=cfg.channel_ready())}\n<div class="wrap"><div class="card"><h2>🩺 自检<span class="hint">离线也可快速体检</span></h2>\n<div class="toolbar">\n<button class="btn primary" onclick="run(\'?quick=1\')">快速自检</button>\n<button class="btn" onclick="run(\'?quick=0\')">完整自检（含网络/来源抽检）</button>\n<button class="btn" onclick="run(\'?quick=1&smtp=1\')">附加 SMTP 握手</button>\n<button class="btn" onclick="fixReg()">修复本地注册</button>\n<a class="chip" href="/">← 首页</a></div>\n<div id="items"><p class="empty">点击上方按钮开始体检。</p></div></div>\n<div class="hint">报告同时落盘 <code>data/logs/selfcheck.txt</code>；本地注册（自启/快捷方式）在常驻运行时也会自动自愈（路径无关设计：软件目录整体搬移后自动改写注册）。</div>\n</div><script>\nfunction run(qs){{var el=document.getElementById("items");el.innerHTML=\'<p class="empty">体检中…</p>\';\nfetch("/api/selfcheck"+qs).then(r=>r.json()).then(d=>{{el.innerHTML=(d.items||[]).map(i=>\'<div class="sc-item"><span class="st">\'+(i.ok?"✅":"⚠️")+\'</span><div class="bd"><b>\'+i.item+\'</b><span>\'+(i.detail||"")+"</span></div></div>").join("")}}).catch(e=>{{el.innerHTML=\'<p class="empty">请求失败</p>\'}})}}\nfunction fixReg(){{fetch("/api/repair",{{method:"POST"}}).then(r=>r.json()).then(d=>alert(d.message))}}\n</script></body></html>'
def render_agent(app):
    """内置 Agent：自然语言下需求 → 抓取/推送工作流（规则模式 + 可选 LLM）。"""
    cfg = app.cfg
    mode = 'LLM 已接入（文章API）' if cfg.article_api_enabled else '本地规则模式（设置页接入文章API 可理解更复杂表述）'
    from .agent import HELP_TEXT as HELP_TEXT_SHORT
    suggestions = ['来源状态', '采集一轮', '立即推送', '订阅 https://www.qbitai.com/feed 的AI内容并推给我', '把库里关于 人形机器人 的内容报一版给我']
    chips = ''.join((f'<a class=\"chip\" href=\"javascript:void(0)\" onclick=\"fill(this.textContent)\">{htm.escape(s)}</a>' for s in suggestions))
    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>Agent · NewsHub</title>\n<link rel="icon" href="/favicon.svg">\n<style>{CSS}</style></head><body>\n{_nav(cfg, "agent", net_ok=cfg.channel_ready())}\n<div class="wrap"><div class="card"><h2>🤖 Agent 工作台<span class="hint">{htm.escape(mode)}</span></h2>\n<div class="chat" id="chat"><div class="msg bot">{htm.escape(HELP_TEXT_SHORT)}</div></div>\n<div class="chatbar"><input id="msg" placeholder="例如：订阅 https://example.com 的机器人内容，抓完推给我" onkeydown="if(event.key===\'Enter\')send()"><button class="btn primary" onclick="send()">发送</button></div>\n<div class="sugg">{chips}</div></div>\n<div class="hint">安全边界：Agent 只操作本地 config/news.db 与已配置的推送通道，不执行任意代码。</div>\n</div><script>\nfunction fill(t){{document.getElementById("msg").value=t;document.getElementById("msg").focus()}}\nfunction send(){{var inp=document.getElementById("msg");var t=inp.value.trim();if(!t)return;\n var c=document.getElementById("chat");\n c.insertAdjacentHTML("beforeend",\'<div class="msg user">\'+t.replace(/</g,"&lt;")+"</div>");\n c.insertAdjacentHTML("beforeend",\'<div class="msg bot" id="waiting">思考中…</div>\');\n c.scrollTop=c.scrollHeight;inp.value="";\n fetch("/api/agent",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{message:t}})}})\n  .then(r=>r.json()).then(d=>{{document.getElementById("waiting").remove();\n   c.insertAdjacentHTML("beforeend",\'<div class="msg bot">[\'+(d.mode||"")+"] "+(d.reply||d.message||"").replace(/</g,"&lt;").replace(/\\n/g,"<br>")+"</div>");\n   c.scrollTop=c.scrollHeight}})\n  .catch(e=>{{document.getElementById("waiting").textContent="请求失败："+e}})}}\n</script></body></html>'
def write_static_dashboard(app):
    try:
        html = render_dashboard(app)(cat='全部', date='全部', search='')
        path = os.path.join(app.data_dir, 'dashboard.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        return path
    except Exception:
        log.warning('静态仪表盘写入失败', exc_info=True)
        return None
def apply_settings(app, body):
    """设置中心保存：推送时刻/SMTP/板块/关键词/文章API（部分更新，写回 config）。"""
    import json
    path = app.cfg.path
    with open(path, 'r', encoding='utf-8-sig') as f:
        disk = json.load(f)
    push = disk.setdefault('推送', {})
    if '推送时刻' in body:
        times = [str(t).strip() for t in body['推送时刻'] if str(t).strip()]
        if times:
            push['推送时刻'] = times
    if 'SMTP' in body:
        s = body['SMTP'] or {}
        sm = push.setdefault('SMTP', {})
        for k in ('服务器', '账号', '收件人'):
            if str(s.get(k, '')).strip():
                sm[k] = str(s[k]).strip()
        if str(s.get('授权码', '')).strip():
            sm['授权码'] = str(s['授权码']).strip()
        try:
            if int(s.get('端口', 0) or 0):
                sm['端口'] = int(s['端口'])
        except (TypeError, ValueError):
            pass
    if '板块' in body:
        boards = body['板块'] or []
        registry_names = {r['name'] for r in SOURCE_REGISTRY}
        custom = [s for s in disk.get('采集', {}).get('来源', []) if s.get('name') not in registry_names]
        disk.setdefault('采集', {})['来源'] = build_sources_config(boards, custom)
    if '自定义关键词' in body:
        boards = body.get('板块') or sorted({s['分类'] for s in disk.get('采集', {}).get('来源', []) if s.get('enabled')})
        kw = build_keywords(boards, body.get('自定义关键词') or [])
        disk.setdefault('过滤', {})['关键词'] = kw
    if '文章API' in body:
        a = body['文章API'] or {}
        disk['文章API'] = {'启用': bool(a.get('启用')), '接口地址': str(a.get('接口地址', '')).strip(), '密钥': str(a.get('密钥', '')).strip(), '模型': str(a.get('模型', '')).strip(), '超时秒': 30, '只处理每类前N条': max(1, min(20, int(a.get('只处理每类前N条', 5) or 5)))}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(disk, f, ensure_ascii=False, indent=2)
    app.cfg.reload()
    return {'ok': True, 'message': '已保存（约 30 秒内生效）'}
def make_server(app):
    """本地服务（127.0.0.1）。首次未完成引导时 / 自动跳转 /setup。"""
    app.first_push_state = {'running': False, 'done': False, 'ok': None, 'msg': ''}

    def _first_push():
        st = app.first_push_state
        try:
            last = app.db.last_successful_push_time()
            if last:
                dt = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - dt).total_seconds() < 600:
                    st.update(done=True, ok=True, running=False, msg='引导期间已自动推送（查收邮箱即可），跳过重复发送')
                    return
            ok, err, n = app.do_push(kind='manual')
            st.update(done=True, ok=ok, running=False, msg=f'已推送 {n} 条' if ok else str(err)[:120])
        except Busy:
            st.update(done=True, ok=False, running=False, msg='有任务在进行，请稍后到首页重推')
        except Exception as e:
            st.update(done=True, ok=False, running=False, msg=str(e)[:120])

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):
            log.debug('%s %s', self.address_string(), fmt % args)

        def _send(self, code, body, ctype='text/html; charset=utf-8'):
            data = body.encode('utf-8') if isinstance(body, str) else body
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

        def _body(self):
            length = int(self.headers.get('Content-Length', 0) or 0)
            try:
                return json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            except (ValueError, json.JSONDecodeError):
                return None

        def do_GET(self):
            try:
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                if u.path == '/' and (not app.cfg.onboarded):
                    self.send_response(302)
                    self.send_header('Location', '/setup')
                    self.end_headers()
                    return
                if u.path == '/':
                    try:
                        limit = max(1, min(500, int(q.get('limit', 200))))
                    except (TypeError, ValueError):
                        limit = 200
                    self._send(200, render_dashboard(app)(cat=q.get('cat', '全部'), date=q.get('date', '全部'), search=q.get('q', ''), limit=limit, month=q.get('m'), view=q.get('view', 'grid')))
                    return
                if u.path == '/setup':
                    self._send(200, render_setup(app))
                    return
                if u.path == '/agent' and app.cfg.onboarded:
                    self._send(200, render_agent(app))
                    return
                if u.path == '/selfcheck' and app.cfg.onboarded:
                    self._send(200, render_selfcheck(app))
                    return
                if u.path == '/favicon.svg':
                    self._send(200, FAVICON_SVG, ctype='image/svg+xml; charset=utf-8')
                    return
                if u.path == '/settings':
                    self._send(200, render_settings(app))
                    return
                if u.path == '/digest' and q.get('date'):
                    self._send(200, render_digest_archive(app, q['date']))
                    return
                if u.path == '/digest':
                    self._send(200, render_digest_preview(app))
                    return
                if u.path == '/api/net':
                    ok = probe_network(timeout=3)
                    self._json({'ok': ok, 'message': '网络正常' if ok else '当前离线'})
                    return
                if u.path == '/api/selfcheck' and app.cfg.onboarded:
                    from .selfcheck import doctor
                    result = doctor(app, quick=q.get('quick') == '1', smtp=q.get('smtp') == '1')
                    result['message'] = '自检完成：全部通过' if result['ok'] else '自检完成：存在需关注项'
                    self._json(result)
                    return
                if u.path == '/api/setup/status':
                    self._json({'ok': True, 'onboarded': app.cfg.onboarded, 'first_push': app.first_push_state})
                    return
                if u.path == '/api/digest' and q.get('date'):
                    self._json({'ok': True, 'date': q['date'], 'digests': app.db.get_digests(q['date'])})
                    return
                if u.path == '/api/digests':
                    self._json({'ok': True, 'dates': app.db.digest_dates()})
                    return
                if u.path == '/api/health':
                    self._json({'ok': True, 'articles': app.db.count(), 'onboarded': app.cfg.onboarded, 'channel': app.cfg.channel_type, 'channel_ready': app.cfg.channel_ready(), 'last_collect_at': str(app.last_collect_at), 'sources': app.db.source_health_all()})
                    return
                self._send(404, '<h1>404</h1>')
            except Exception:
                log.exception('GET %s 处理失败', self.path)
                try:
                    self._send(500, '<h1>内部错误，详见日志</h1>')
                except Exception:
                    return

        def do_POST(self):
            try:
                u = urlparse(self.path)
                if u.path == '/api/setup/test-smtp':
                    body = self._body()
                    s = (body or {}).get('SMTP') or {}
                    ok, err = verify_smtp(s.get('服务器', ''), s.get('端口', 465), s.get('账号', ''), s.get('授权码', ''), s.get('收件人', ''))
                    self._json({'ok': ok, 'message': '握手成功：登录有效，测试邮件已发出，请查收！' if ok else f'握手失败：{err}'})
                    return
                if u.path == '/api/setup/skip':
                    from .core import apply_skip
                    ok, err = apply_skip(app.cfg.path)
                    if ok:
                        app.cfg.reload(force=True)
                    self._json({'ok': ok, 'message': err or '已跳过引导'}, 200 if ok else 400)
                    return
                if u.path == '/api/setup/finish':
                    body = self._body()
                    ok, err = apply_onboarding(app.cfg.path, body or {})
                    if not ok:
                        self._json({'ok': False, 'message': err}, 400)
                        return
                    app.cfg.reload()
                    app.first_push_state.update(running=False, done=False, ok=None, msg='')
                    threading.Thread(target=_first_push, daemon=True).start()
                    self._json({'ok': True, 'message': '配置已保存，第一期简讯生成中'})
                    return
                if u.path == '/api/settings':
                    body = self._body()
                    if body is None:
                        self._json({'ok': False, 'message': '参数错误'}, 400)
                        return
                    self._json(apply_settings(app, body))
                    return
                if u.path == '/api/collect':
                    threading.Thread(target=write_static_dashboard, args=(app,), daemon=True).start()
                    try:
                        stats = app.run_collection()
                        ok = sum((1 for s in stats.values() if s['ok']))
                        self._json({'ok': True, 'message': f'采集完成：{ok}/{len(stats)} 个来源正常，新增 {sum((s["count"] for s in stats.values()))} 条'})
                    except Busy as e:
                        self._json({'ok': False, 'message': str(e)}, 409)
                    return
                if u.path == '/api/push-now':
                    try:
                        ok, err, n = app.do_push(kind='manual')
                        self._json({'ok': ok, 'message': f'推送{"成功" if ok else "失败"}（{n} 条）' + (f'：{err}' if err else '')})
                    except Busy as e:
                        self._json({'ok': False, 'message': str(e)}, 409)
                    return
                if u.path == '/api/test-push':
                    ok, err = app.send_test_push()
                    self._json({'ok': ok, 'message': '测试简讯已发送，请查收邮箱' if ok else f'发送失败：{err}'})
                    return
                if u.path == '/api/quick-send':
                    body = self._body()
                    files_meta = (body or {}).get('files') or []
                    if not files_meta:
                        self._json({'ok': False, 'message': '没有文件'}, 400)
                        return
                    if len(files_meta) > 5:
                        self._json({'ok': False, 'message': '单次最多 5 个文件'}, 400)
                        return
                    import base64
                    from .push import PushError
                    try:
                        files = []
                        total = 0
                        for f in files_meta[:5]:
                            blob = base64.b64decode(str(f.get('data', '') or ''))
                            total += len(blob)
                            if not blob:
                                raise ValueError(f"文件 {f.get('name', '?')} 内容为空")
                            files.append((str(f.get('name', 'file')), blob))
                        if total > 15728640:
                            raise ValueError('总大小超过 15MB 上限')
                    except Exception as e:
                        self._json({'ok': False, 'message': f'文件解析失败：{e}'}, 400)
                        return
                    if app.cfg.channel_type != 'smtp':
                        self._json({'ok': False, 'message': f'文件直发仅支持 SMTP 邮箱通道（当前 {app.cfg.channel_type}）'}, 400)
                        return
                    ch = SmtpChannel(app.cfg.smtp, timeout=app.cfg.send_timeout)
                    ok, err = ch.send_files(files, note=str((body or {}).get('note', '')))
                    names = '、'.join((n for n, _ in files))
                    app.db.record_push('quick', 'success' if ok else 'failed', 'smtp', '', '', len(files), f'文件直发 {names[:200]}')
                    self._json({'ok': ok, 'message': f'已发送到邮箱（{len(files)} 个文件）' if ok else f'发送失败：{err}'})
                    return
                if u.path == '/api/repair':
                    from .selfcheck import repair_registration
                    ok, lines = repair_registration()
                    self._json({'ok': ok, 'message': '本地注册已就绪：' + '；'.join(lines) if lines else '本地注册已就绪'})
                    return
                if u.path == '/api/agent':
                    body = self._body()
                    msg_text = str((body or {}).get('message', '')).strip()
                    if not msg_text:
                        self._json({'ok': False, 'message': '请输入需求'}, 400)
                        return
                    from . import agent as agent_mod
                    plan = agent_mod.plan_message(msg_text, app.cfg)
                    reply = agent_mod.execute(app, plan)
                    mode = 'LLM 解析' if plan.get('mode') == 'llm' else '规则解析'
                    self._json({'ok': True, 'reply': reply, 'mode': mode, 'steps': plan.get('steps', [])})
                    return
                self._json({'ok': False, 'message': '未知接口'}, 404)
            except Busy as e:
                self._json({'ok': False, 'message': str(e)}, 409)
    server = ThreadingHTTPServer(('127.0.0.1', app.cfg.dashboard_port), Handler)
    server.daemon_threads = True
    return server
