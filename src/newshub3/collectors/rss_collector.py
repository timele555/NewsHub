"""collectors.rss_collector —— 通用 RSS 采集（feedparser）。\n\n覆盖来源：量子位 / 少数派 / 爱范儿 / IEEE Spectrum 机器人 / The Robot Report，\n以及用户在 config 中自定义的 custom_rss（如 RSSHub 桥接的机器之心、36氪）。\n"""
import logging
from urllib.parse import urljoin
import feedparser
from .base import Item, FetchError, fetch, clean_text, to_local_dt
log = logging.getLogger('newshub3.collect.rss')
def collect_rss(source, cfg, fetched_text=None):
    """采集一个 RSS 源。fetched_text 供离线测试注入 fixture，跳过网络。"""
    if fetched_text is None:
        resp = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval)
        payload = resp.content
    else:
        payload = fetched_text.encode('utf-8') if isinstance(fetched_text, str) else fetched_text
    try:
        fp = feedparser.parse(payload)
    except Exception as e:
        raise FetchError(f'RSS 解析失败: {e}') from e
    if fp.bozo and not fp.entries:
        raise FetchError(f'RSS 无有效条目: {getattr(fp, "bozo_exception", "未知")}')
    base_link = getattr(fp, 'feed', None) or getattr(fp.feed, 'link', '') or source['url']
    items, seen = [], set()
    for e in fp.entries[:cfg.per_source_limit * 2]:
        title = clean_text(getattr(e, 'title', ''), 120)
        link = clean_text(getattr(e, 'link', ''), 500)
        if not title or not link:
            continue
        if link.startswith('//'):
            link = 'https:' + link
        elif not link.startswith('http'):
            link = urljoin(base_link, link)
        if link in seen:
            continue
        seen.add(link)
        summary_raw = getattr(e, 'summary', '') or getattr(e, 'description', '') or ''
        summary = clean_text(summary_raw, cfg.summary_maxlen)
        if summary and (summary in title or title in summary):
            summary = ''
        pub = None
        for attr in ('published_parsed', 'updated_parsed'):
            pub = to_local_dt(getattr(e, attr, None))
            if pub:
                break
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=link, summary=summary, published_at=pub))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('RSS 条目数为 0')
    return items
