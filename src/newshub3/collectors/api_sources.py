"""collectors.api_sources —— gateway/API 型来源（虎嗅、华尔街见闻）。"""
import logging
from .base import Item, FetchError, fetch, clean_text, ts_to_local_dt
log = logging.getLogger('newshub3.collect.api')
def collect_huxiu(source, cfg, fetched_json=None):
    """虎嗅：官方 web 接口 api-article.huxiu.com，platform=www。"""
    if fetched_json is None:
        r = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval, params={'platform': 'www', 'article_type': '1', 'pagesize': min(22, cfg.per_source_limit), 'page': '1'})
        try:
            fetched_json = r.json()
        except ValueError as e:
            raise FetchError('接口返回非 JSON') from e
    if not (isinstance(fetched_json, dict) and fetched_json.get('success')):
        raise FetchError(f'接口返回异常: {str(fetched_json)[:120]}')
    items, seen = [], set()
    for it in (fetched_json.get('data', {}) or {}).get('dataList', []) or []:
        aid = str(it.get('aid', '')).strip()
        title = clean_text(it.get('title'), 150)
        if not title or not aid:
            continue
        url = clean_text(it.get('share_url'), 500) or f'https://www.huxiu.com/article/{aid}.html'
        if url in seen:
            continue
        seen.add(url)
        if str(it.get('is_sponsor', '0')) == '1':
            continue
        summary = clean_text(it.get('summary'), cfg.summary_maxlen)
        if summary and (summary in title or title in summary):
            summary = ''
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=url, summary=summary, published_at=ts_to_local_dt(it.get('dateline'))))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('接口条目为 0')
    return items
def collect_wscn(source, cfg, fetched_json=None):
    """华尔街见闻：公开快讯接口 /apiv1/content/lives（channel=global-channel）。"""
    if fetched_json is None:
        r = fetch(source['url'], timeout=cfg.http_timeout, retries=cfg.retries, retry_interval=cfg.retry_interval, params={'channel': 'global-channel', 'limit': min(30, cfg.per_source_limit)})
        try:
            fetched_json = r.json()
        except ValueError as e:
            raise FetchError('接口返回非 JSON') from e
    if not (isinstance(fetched_json, dict) and fetched_json.get('code') == 20000):
        raise FetchError(f'接口返回异常: {str(fetched_json)[:120]}')
    items, seen = [], set()
    for it in (fetched_json.get('data', {}) or {}).get('items', []) or []:
        uri = clean_text(it.get('uri'), 500)
        if not uri or not uri.startswith('http') or uri in seen:
            continue
        seen.add(uri)
        title = clean_text(it.get('title'), 120) or clean_text(it.get('highlight_title'), 120)
        summary = clean_text(it.get('content_text'), cfg.summary_maxlen)
        if not title:
            if not summary:
                continue
            title = summary[:40]
        if summary and (summary in title or title in summary):
            summary = ''
        items.append(Item(category=source.get('分类', '未分类'), source=source['name'], title=title, url=uri, summary=summary, published_at=ts_to_local_dt(it.get('display_time'))))
        if len(items) >= cfg.per_source_limit:
            break
    if not items:
        raise FetchError('接口条目为 0')
    return items
