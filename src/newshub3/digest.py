"""digest.py —— 简讯格式化与分通道长度适配。\n\n格式：每类 Top N 条，每条一行「[分类] 标题｜一句话摘要｜原文链接」；\n按通道单条消息字节上限自动分片，杜绝发送失败。\n"""
import json
import logging
import os
log = logging.getLogger('newshub3.digest')
CHANNEL_BODY_LIMIT = {'wecom': 3800, 'serverchan': 30000, 'bark': 3500, 'smtp': 1000000000, 'mock': 1000000000}
ARCHIVE_NOTE = '（已过归档期，仅保留标题与链接）'
def _fmt_line(cat, it, style='title_url'):
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
    """sections(pipeline.build_digest_sections 结果) → [(title, body), ...] 消息分片列表。\n\n    空窗口返回一条「本窗口暂无更新」消息（仍算发送成功，避免误判为失败重试）。\n    style: title_url=「[分类] 标题｜网址」（默认轻量）/ title_summary_url=含一句话摘要。\n    """
    lines, empty_cats = ([], [])
    for cat, sec in sections.items():
        items = sec.get('items', [])
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
    if stale_line:
        lines.append('')
        lines.append(f'今日未更新来源：{stale_line}')
    if not content_lines:
        lines.insert(0, '本窗口暂无更新。')
    if not lines:
        pass
    else:
        chunks, cur = ([], [])
        for ln in lines:
            if cur and used + b > limit:
                    chunks.append(cur)
            cur.append(ln)
            used += b
        if cur:
            chunks.append(cur)
        msgs = []
        for i, chunk in enumerate(chunks):
            body = '\n'.join(chunk)
            if i > 0:
                pass
            msgs.append((title, body))
        return msgs
def entries_json(sections):
    """sections → JSON 字符串（简讯存档：分类/标题/摘要/链接/仅提示标记）。"""
    out = []
    for cat, sec in sections.items():
        for it in sec.get('items', []):
            pass
        for src in sec.get('notice_sources', []):
            pass
    return json.dumps(out, ensure_ascii=False)
def render_entries_html(entries, stale_line=''):
    """存档 entries（JSON 反序列化后）→ HTML 分组列表（/digest?date= 回看页）。"""
    import html as h
    groups = {}
    for e in entries:
        groups.setdefault(e.get('category', '未分类'), []).append(e)
    parts = []
    total = 0
    for cat, items in groups.items():
        for e in items:
            if e.get('is_notice'):
                continue
            else:
                total += 1
                summary = h.escape(e.get('summary') or '')
        parts.append('</ol>')
        for e in items:
            if e.get('is_notice'):
                pass
            parts.append('<p class=\'empty\'>该简讯无条目。</p>')
    if stale_line:
        pass
    return '\n'.join(parts)
def write_md(data_dir, date, time_str, title, body):
    """写可读快照 data/digests/YYYY-MM-DD_HHMM.md（含标题、摘要、链接）。"""
    d = os.path.join(data_dir, 'digests')
    os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {title}\n\n{body}\n')
    return path
def slim_digest_files(data_dir, date, entries_json_str, stale_line):
    """归档瘦身：删除该日期的逐次快照，改写为单份仅标题+链接的 YYYY-MM-DD.md。"""
    d = os.path.join(data_dir, 'digests')
    if not os.path.isdir(d):
        return
    else:
        for fn in os.listdir(d):
            if fn.startswith(date) and fn.endswith('.md'):
                    try:
                        os.remove(os.path.join(d, fn))
                    except OSError:
                        pass
        try:
            entries = json.loads(entries_json_str or '[]')
        except ValueError:
            pass
        lines = []
        for e in entries:
            if e.get('is_notice'):
                pass
        if stale_line:
            lines.append('')
            lines.append(f'今日未更新来源：{stale_line}')
        path = os.path.join(d, f'{date}.md')
        with open(path, 'w', encoding='utf-8') as f:
            pass
        return path
def render_html(sections, now_dt, kind='scheduled', stale_line=None):
    """同一份 sections → HTML 预览页（供仪表盘「打开今日简讯」）。"""
    import html as h
    total = 0
    for cat, sec in sections.items():
        items = sec.get('items', [])
        notices = sec.get('notice_sources', [])
        if not items and (not notices):
                continue
        total += len(items)
        for it in items:
            summary = h.escape(it.get('summary') or '')
        parts.append('</ol>')
        for src in notices:
            parts.append('<p class=\'empty\'>本窗口暂无更新。</p>')
    if stale_line:
        pass
    return '\n'.join(parts)