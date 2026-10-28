"""digest.py —— 简讯格式化与分通道长度适配。\n\n格式：每类 Top N 条，每条一行「[分类] 标题｜一句话摘要｜原文链接」；\n按通道单条消息字节上限自动分片，杜绝发送失败。\n"""
import json
import logging
import os
log = logging.getLogger('newshub3.digest')
CHANNEL_BODY_LIMIT = {'wecom': 3800, 'serverchan': 30000, 'bark': 3500, 'smtp': 1000000000, 'mock': 1000000000}
ARCHIVE_NOTE = '（已过归档期，仅保留标题与链接）'
def _fmt_line(cat, it, style='title_url'):
    title = it.get('title', '').strip()[:120]
    url = it.get('url', '').strip()
    if style == 'title_summary_url':
        summary = (it.get('summary') or '').strip()[:100]
        line = f'[{cat}] {title}'
        if summary:
            line += f'｜{summary}'
        line += f'｜{url}'
        return line
    else:
        line = f'[{cat}] {title}｜{url}'
        return line
def _header(now_dt, kind='scheduled'):
    tag = {'scheduled': '', 'catchup': '【补发】', 'test': '【测试】', 'manual': '【手动】'}.get(kind, '')
    return f'📰 NewsHub 简讯 {tag}{now_dt.strftime("%m-%d %H:%M")}'
def build_messages(sections, now_dt, channel, kind='scheduled', stale_line=None, body_limit=None, style='title_url'):
    """sections(pipeline.build_digest_sections 结果) → [(title, body), ...] 消息分片列表。

    空窗口返回一条「本窗口暂无更新」消息（仍算发送成功，避免误判为失败重试）。
    style: title_url=「[分类] 标题｜网址」（默认轻量）/ title_summary_url=含一句话摘要。
    """
    lines, empty_cats = ([], [])
    limit = body_limit or CHANNEL_BODY_LIMIT.get(channel, 3800)
    for cat, sec in sections.items():
        items = sec.get('items', []) or []
        if not items and (not sec.get('notice_sources')):
            empty_cats.append(cat)
            continue
        for it in items:
            lines.append(_fmt_line(cat, it, style))
        for src in sec.get('notice_sources', []):
            lines.append(f'[{cat}] {src}：今日有更新（付费源，仅提示）')
    if empty_cats:
        lines.append('（以下分类暂无更新：' + '、'.join(empty_cats) + '）')
    header = _header(now_dt, kind)
    content_lines = [l for l in lines if not l.startswith('（以下分类暂无更新')]
    if stale_line:
        lines.append('')
        lines.append(f'今日未更新来源：{stale_line}')
    if not content_lines:
        lines.insert(0, '本窗口暂无更新。')
    if not lines:
        return [('本窗口暂无更新。', '本窗口暂无更新。')]
    chunks, cur = ([], [])
    used = len(header.encode('utf-8')) + 20
    for ln in lines:
        b = len(ln.encode('utf-8')) + 1
        if cur and used + b > limit:
            chunks.append(cur)
            cur = []
            used = len(header.encode('utf-8')) + 20
        cur.append(ln)
        used += b
    if cur:
        chunks.append(cur)
    msgs = []
    for i, chunk in enumerate(chunks):
        title = header if i == 0 else f'{header}（{i + 1}/{len(chunks)}）'
        body = '\n'.join(chunk)
        if i > 0:
            body = f'（续 {i + 1}/{len(chunks)}）\n' + body
        msgs.append((title, body))
    return msgs
def entries_json(sections):
    """sections → JSON 字符串（简讯存档：分类/标题/摘要/链接/仅提示标记）。"""
    out = []
    for cat, sec in sections.items():
        for it in sec.get('items', []):
            out.append({'category': cat, 'title': it.get('title', ''), 'summary': it.get('summary') or '', 'url': it.get('url', ''), 'is_notice': False})
        for src in sec.get('notice_sources', []):
            out.append({'category': cat, 'title': src, 'summary': '', 'url': '', 'is_notice': True})
    return json.dumps(out, ensure_ascii=False)
def render_entries_html(entries, stale_line=''):
    import html as h
    groups = {}
    for e in entries:
        groups.setdefault(e.get('category', '未分类'), []).append(e)
    parts = []
    total = 0
    for cat, items in groups.items():
        parts.append(f'<h2>{h.escape(cat)}</h2><ol>')
        for e in items:
            if e.get('is_notice'):
                continue
            total += 1
            summary = h.escape(e.get('summary') or '')
            parts.append(f'<li><a href="{h.escape(e.get("url", ""), quote=True)}" target="_blank" rel="noopener">{h.escape(e.get("title", ""))}</a>' + (f'<span class="sum">｜{summary}</span></li>' if summary else '</li>'))
        parts.append('</ol>')
        for e in items:
            if not e.get('is_notice'):
                continue
            parts.append(f'<p class="notice">🔔 {h.escape(e.get("title", ""))}：今日有更新（付费源，仅提示）</p>')
    if total == 0 and not any((e.get('is_notice') for e in entries)):
        parts.append("<p class='empty'>该简讯无条目。</p>")
    if stale_line:
        parts.append(f"<p class='stale'>今日未更新来源：{h.escape(stale_line)}</p>")
    return ''.join(parts)
def write_md(data_dir, date, time_str, title, body):
    """写可读快照 data/digests/YYYY-MM-DD_HHMM.md（含标题、摘要、链接）。"""
    d = os.path.join(data_dir, 'digests')
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f'{date}_{time_str.replace(":", "")}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {title}\n\n{body}\n')
    return path
def slim_digest_files(data_dir, date, entries_json_str, stale_line):
    d = os.path.join(data_dir, 'digests')
    if not os.path.isdir(d):
        return None
    for fn in os.listdir(d):
        if not (fn.startswith(date) and fn.endswith('.md')):
            continue
        try:
            os.remove(os.path.join(d, fn))
        except OSError:
            pass
    try:
        entries = json.loads(entries_json_str or '[]')
    except ValueError:
        entries = []
    lines = []
    for e in entries:
        if e.get('is_notice'):
            lines.append(f"[{e.get('category', '')}] {e.get('title', '')}：今日有更新（付费源，仅提示）")
        else:
            lines.append(f"[{e.get('category', '')}] {e.get('title', '')}｜{e.get('url', '')}")
    if stale_line:
        lines.append('')
        lines.append(f'今日未更新来源：{stale_line}')
    path = os.path.join(d, f'{date}.md')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'# 简讯归档 {date} {ARCHIVE_NOTE}\n\n' + '\n'.join(lines) + '\n')
    except OSError:
        return None
    return path
def render_html(sections, now_dt, kind='scheduled', stale_line=None):
    import html as h
    parts = [f'<h1>📰 NewsHub 简讯 <small>{h.escape(_header(now_dt, kind)[len("📰 NewsHub 简讯"):].strip())}</small></h1>']
    total = 0
    for cat, sec in sections.items():
        items = sec.get('items', [])
        notices = sec.get('notice_sources', [])
        if not items and not notices:
            continue
        total += len(items)
        parts.append(f'<h2>{h.escape(cat)}</h2><ol>')
        for it in items:
            summary = h.escape(it.get('summary') or '')
            parts.append(f'<li><a href="{h.escape(it.get("url", ""), quote=True)}" target="_blank">{h.escape(it.get("title", ""))}</a>' + (f'<span class="sum">｜{summary}</span>' if summary else '') + (f'<span class="hits">{" / ".join(it.get("_hits", []))}</span>' if it.get('_hits') else '') + '</li>')
        parts.append('</ol>')
        for src in notices:
            parts.append(f'<p class="notice">🔔 {h.escape(src)}：今日有更新（付费源，仅提示）</p>')
    if total == 0 and not any((s.get('notice_sources') for s in sections.values())):
        parts.append("<p class='empty'>本窗口暂无更新。</p>")
    if stale_line:
        parts.append(f"<p class='stale'>今日未更新来源：{h.escape(stale_line)}</p>")
    return ''.join(parts)
