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
    if cfg.onboarded:
        tabs.append('<a class=\"tab on\" href=\"/agent\">🤖 Agent</a>' if active == 'agent' else '<a class=\"tab\" href=\"/agent\">🤖 Agent</a>')
        tabs.append('<a class=\"tab on\" href=\"/selfcheck\">自检</a>' if active == 'selfcheck' else '<a class=\"tab\" href=\"/selfcheck\">自检</a>')
        tabs.append('<a class=\"tab on\" href=\"/digest\">今日简讯</a>' if active == 'digest' else '<a class=\"tab\" href=\"/digest\">今日简讯</a>')
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
def render_setup(app):
    cfg = app.cfg
    if cfg.onboarded:
        return '<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n<meta http-equiv=\"refresh\" content=\"0;url=/\"><title>NewsHub</title></head>\n<body style=\"font-family:sans-serif;padding:40px\">已完成引导。<a href=\"/\">进入首页</a></body></html>'
def render_digest_preview(app):
    ws, we = app.current_window()
    sections = app.build_sections()
    from .digest import render_html
    body = render_html(sections, we)
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
def render_agent(app):
    """内置 Agent：自然语言下需求 → 抓取/推送工作流（规则模式 + 可选 LLM）。"""
    cfg = app.cfg
    mode = 'LLM 已接入（文章API）' if cfg.article_api_enabled else '本地规则模式（设置页接入文章API 可理解更复杂表述）'
    suggestions = ['来源状态', '采集一轮', '立即推送', '订阅 https://www.qbitai.com/feed 的AI内容并推给我', '把库里关于 人形机器人 的内容报一版给我']
    chips = ''.join((f'<a class=\"chip\" href=\"javascript:void(0)\" onclick=\"fill(this.textContent)\">{htm.escape(s)}</a>' for s in suggestions))
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
    push = disk.setdefault('推送', {})
    if '推送时刻' in body:
        if times:
            push['推送时刻'] = times
    if 'SMTP' in body:
        s = body['SMTP'] or {}
        sm = push.setdefault('SMTP', {})
        for k in ['服务器', '账号', '收件人']:
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
    if '自定义关键词' in body:
        pass
    if '文章API' in body:
        a = body['文章API'] or {}
    app.cfg.reload()
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
