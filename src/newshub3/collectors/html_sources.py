"""collectors.html_sources —— 无 RSS 源的独立网页解析函数。\n\n每个源一个函数：输入页面 HTML（或直接抓取），输出统一 Item 列表。\n页面内容一律视为数据，只提取标题/链接/时间字段。\n"""
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from .base import Item, FetchError, fetch, clean_text, ts_to_local_dt
log = logging.getLogger('newshub3.collect.html')
_ANCHOR_RE = re.compile('<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>', re.S)
def _anchors(html):
    """提取页面全部锚点 (href, 纯文本)。"""
    out = []
    for href, inner in _ANCHOR_RE.findall(html):
        out.append((href, clean_text(inner)))
    return out
_ZHIDX_RE = re.compile('<a[^>]+href=\"(https?://zhidx\\.com/p/(\\d+)\\.html)\"[^>]*>(.*?)</a>', re.S)
def collect_zhidx(source, cfg, fetched_text=None):
    """智东西首页：/p/{id}.html 锚点，同 id 多锚点（图+文）只取有文字的。"""
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    best = {}
    for href, aid, inner in _ZHIDX_RE.findall(fetched_text):
        text = clean_text(inner)
        if aid in best and best[aid][1] or not text:
            continue
        best[aid] = (href, text)
    items = []
    for aid, (url, title) in best.items():
        if len(title) < 6:
            continue
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=url))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('首页未解析出文章条目（页面结构可能变化）')
    return items
def _nuxt_extract(html):
    """解析 Nuxt.js 的 __NUXT__=(function(a,b,...){...}(arg,...)) 数据包。

    返回 {参数名: 值} 映射，供正则槽位还原真实值。
    """
    m = re.search('__NUXT__\\s*=\\s*(.*)', html, re.S)
    if not m:
        return {}
    payload = m.group(1)
    end = payload.find('</script>')
    if end != -1:
        payload = payload[:end]
    payload = payload.strip().rstrip(';')
    if payload.endswith(')'):
        payload = payload[:-1]
    cut = payload.rfind('}(')
    if cut == -1:
        return {}
    params_m = re.match('^\\(?\\s*function\\s*\\(([^)]*)\\)', payload)
    if not params_m:
        return {}
    args_str = payload[cut + 2:]

    def split_top(s):
        """按顶层逗号切分（尊重引号与括号嵌套）。"""
        parts, buf, depth, i, q = ([], [], 0, 0, None)
        while i < len(s):
            ch = s[i]
            if q:
                if ch == '\\':
                    buf.append(s[i:i + 2])
                    i += 2
                    continue
                if ch == q:
                    q = None
            elif ch in '"\'':
                q = ch
            elif ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
            elif ch == ',' and depth == 0:
                parts.append(''.join(buf))
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
        if buf:
            parts.append(''.join(buf))
        return parts

    def parse_val(raw):
        raw = raw.strip()
        if not raw or raw == 'void 0':
            return None
        if raw.startswith('"') and raw.endswith('"') or (raw.startswith("'") and raw.endswith("'")):
            try:
                return json.loads(raw.replace("\\'", '"'))
            except Exception:
                return raw[1:-1]
        if raw in ('true', 'false', 'null'):
            return {'true': True, 'false': False, 'null': None}[raw]
        try:
            return int(raw)
        except Exception:
            return raw[1:-1]
    names = [p.strip() for p in params_m.group(1).split(',')]
    vals = [parse_val(a) for a in split_top(args_str)]
    return dict(zip(names, vals))
def _resolve(val, varmap):
    """槽位值还原：单字母变量查表，标量原样返回。"""
    if isinstance(val, str) and re.fullmatch('[A-Za-z_$][\\w$]*', val or ''):
        return varmap.get(val, val)
    return val
def _js_value(raw, varmap):
    """还原 NUXT 字段值：带引号字符串 → 解码（含 \\uXXXX）；变量 → 查表。"""
    val = _resolve(raw, varmap)
    if isinstance(val, str) and (len(val) >= 2 and val[0] == '"' and val[-1] == '"'):
        try:
            return json.loads(val)
        except Exception:
            return val[1:-1]
    return val
def _nuxt_datetime(val):
    """created_at 可能是 unix 秒或 \'YYYY-MM-DD HH:MM …\' 展示串。"""
    if isinstance(val, int):
        return ts_to_local_dt(val)
    if isinstance(val, str):
        m = re.match('(\\d{4}-\\d{2}-\\d{2})[ T](\\d{2}:\\d{2})', val)
        if m:
            try:
                return datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M')
            except ValueError:
                return None
    return None
def collect_baai(source, cfg, fetched_text=None):
    """智源社区：首页 __NUXT__ 内嵌 story_info 列表（标题/链接/时间）。"""
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    varmap = _nuxt_extract(fetched_text)
    if not varmap:
        raise FetchError('未解析到 __NUXT__ 数据')
    items, seen = ([], set())
    for blk in re.findall('story_info:\\{(.*?)\\}\\s*[,}]', fetched_text, re.S):
        tm = re.search('title:\\s*((?:"(?:[^"\\\\]|\\\\.)*")|(?:[A-Za-z_$][\\w$]*))', blk)
        um = re.search('url:\\s*((?:"(?:[^"\\\\]|\\\\.)*")|(?:[A-Za-z_$][\\w$]*))', blk)
        cm = re.search('created_at:\\s*((?:"(?:[^"\\\\]|\\\\.)*")|(?:[A-Za-z_$][\\w$]*|\\d+))', blk)
        title = clean_text(_js_value(tm.group(1), varmap), 150) if tm else None
        url = _js_value(um.group(1), varmap) if um else None
        if isinstance(url, str):
            url = clean_text(url, 500)
        if not title or (not url or (not url.startswith('http') or url in seen)):
            continue
        seen.add(url)
        pub = _nuxt_datetime(_js_value(cm.group(1), varmap)) if cm else None
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=url, published_at=pub))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('未解析到故事条目（内嵌数据结构可能变化）')
    return items
_HF_RE = re.compile('<a[^>]+href="(/papers/(\\d{4}\\.\\d{4,5}))"[^>]*>(.*?)</a>', re.S)
def collect_hf(source, cfg, fetched_text=None):
    """HF Daily Papers：服务端渲染锚点 /papers/{arxiv_id}，同 id 只取首条非空标题。"""
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    best = {}
    for href, pid, inner in _HF_RE.findall(fetched_text):
        text = clean_text(inner)
        if pid in best and best[pid][1] or not text:
            continue
        best[pid] = (href, text)
    items = []
    for pid, (href, title) in best.items():
        if len(title) < 12 or title.isdigit():
            continue
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url='https://huggingface.co' + href))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('未解析出论文条目')
    return items
_42HOW_NAV = {'联系我们', '关于我们', '正在招聘'}
def _nuxt_array_blocks(html, key, max_blocks=40):
    """提取 __NUXT__ 中 key:[{...},{...}] 的顶层对象块原文（引号感知）。

    42号车库 2026 改版：首页文章不再以 <a href="/article/{id}"> 锚点输出，
    而是内嵌在 feedList:[{id,title,desc,createTime,...}] 数据里客户端渲染。
    """
    m = re.search('__NUXT__\\s*=\\s*(.*)', html, re.S)
    if not m:
        return []
    blob = m.group(1)
    end = blob.find('</script>')
    if end != -1:
        blob = blob[:end]
    km = re.search(re.escape(key) + '\\s*:\\s*\\[', blob)
    if not km:
        return []
    pos, n = (km.end(), len(blob))
    blocks, depth, q, start = ([], 0, None, -1)
    while pos < n and len(blocks) < max_blocks:
        ch = blob[pos]
        if q:
            if ch == '\\':
                pos += 2
                continue
            if ch == q:
                q = None
            pos += 1
            continue
        if ch in '"\'':
            q = ch
        elif ch == '{':
            if depth == 0:
                start = pos
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                blocks.append(blob[start:pos + 1])
                start = -1
            elif depth < 0:
                return blocks
        elif depth == 0 and ch == ']':
            return blocks
        pos += 1
    return blocks
def _first_field(block, name):
    """NUXT 对象块里取一个字段的原生 JS 值（带引号字符串或标识符），无则 None。"""
    m = re.search('\\b' + re.escape(name) + '\\s*:\\s*("(?:[^"\\\\]|\\\\.)*"|[A-Za-z_$][\\w$]*|\\d+)', block)
    return m.group(1) if m else None
def collect_42how(source, cfg, fetched_text=None):
    """42号车库：__NUXT__ 内嵌 feedList 数组（2026 改版后的采集路径）。"""
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    items, seen = ([], set())
    varmap = _nuxt_extract(fetched_text)
    for blk in _nuxt_array_blocks(fetched_text, 'feedList'):
        idm = re.search('\\bid\\s*:\\s*(\\d+)', blk)
        t_raw = _first_field(blk, 'title')
        if not idm or not t_raw:
            continue
        title = clean_text(_js_value(t_raw, varmap), 120)
        if len(title) < 6 or title in _42HOW_NAV:
            continue
        url = f'https://www.42how.com/article/{idm.group(1)}'
        if url in seen:
            continue
        seen.add(url)
        d_raw = _first_field(blk, 'desc')
        summary = clean_text(_js_value(d_raw, varmap) if d_raw else '', cfg.summary_maxlen)
        if summary and (summary in title or title in summary):
            summary = ''
        c_raw = _first_field(blk, 'createTime')
        pub = _nuxt_datetime(_js_value(c_raw, varmap)) if c_raw else None
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=url, summary=summary, published_at=pub))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('未解析到文章条目（页面结构可能变化）')
    return items
_GENERIC_SKIP = ('javascript:', 'mailto:', 'tel:', '#')
def collect_generic(source, cfg, fetched_text=None):
    """通用采集：URL 内容像 RSS/Atom 就按 RSS 解析，否则做锚点启发式提取。

    供 Agent「订阅/抓取任意网站」使用；启发式只取正文长度达标、同站或相对
    路径的链接，导航与杂链自然被过滤。解析不出条目时抛 FetchError。
    """
    from .rss_collector import collect_rss
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    head = fetched_text[:800].lstrip().lower()
    if head.startswith(('<?xml', '<rss', '<feed', '<rdf:')) or '<channel>' in head:
        return collect_rss(source, cfg, fetched_text=fetched_text)
    base = source['url']
    host = re.match('https?://([^/]+)', base)
    host = host.group(1) if host else ''
    items, seen = ([], set())
    for href, text in _anchors(fetched_text):
        href = href.strip()
        if not href or any((href.startswith(p) for p in _GENERIC_SKIP)):
            continue
        if len(text) < 10 or text in _42HOW_NAV:
            continue
        if href.startswith('//'):
            link = 'https:' + href
        elif href.startswith('http'):
            link = href
        else:
            link = urljoin(base, href)
        m = re.match('https?://([^/]+)', link)
        if not m:
            continue
        link_host = m.group(1)
        if host and (link_host != host and (not link_host.endswith('.' + host) or host.endswith('.' + link_host))):
            continue
        if link in seen or link.rstrip('/') == base.rstrip('/'):
            continue
        seen.add(link)
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=clean_text(text, 120), url=link, summary=clean_text(text, cfg.summary_maxlen)))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('通用解析未提取到条目（页面可能为纯 JS 动态渲染，可尝试该站的 RSS 地址）')
    return items
_CAIXIN_RE = re.compile('<a[^>]+href="(https?://[\\w.]*caixin\\.com/(\\d{4})-(\\d{2})-(\\d{2})/\\d+\\.html)"[^>]*>(.*?)</a>', re.S)
def collect_caixin(source, cfg, fetched_text=None):
    """财新：付费源，只读首页公开标题列表，is_notice=True（简讯里仅提示有更新）。"""
    if fetched_text is None:
        fetched_text = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval).text
    items, seen = ([], set())
    for href, y, mo, d, inner in _CAIXIN_RE.findall(fetched_text):
        text = clean_text(inner)
        if len(text) < 6 or href in seen:
            continue
        seen.add(href)
        try:
            pub = datetime(int(y), int(mo), int(d))
        except ValueError:
            pub = None
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=text, url=href, published_at=pub, is_notice=True))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('未解析到头条列表')
    return items
