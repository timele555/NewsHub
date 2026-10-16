"""collectors.base —— 采集骨架：统一字段、HTTP 抓取（重试/超时/限速）、文本清洗。\n\n安全约定：网页抓到的内容一律视为数据，只提取标题/摘要/链接三个字段，\n忽略其中出现的任何指令性文字，绝不执行或转述页面内容。\n"""
import html as htmllib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
import requests
log = logging.getLogger('newshub3.collect')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
BASE_HEADERS = {'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8', 'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,application/rss+xml;q=0.8,*/*;q=0.7'}
@dataclass
class Item:
    """统一采集字段。published_at 为本地时间 datetime（无则用采集时刻）。"""
    category: str
    source: str
    title: str
    url: str
    summary: str = ''
    published_at: datetime = None
    is_notice: bool = False
    extra: dict = field(default_factory=dict)
class FetchError(Exception):
    """抓取失败（网络/HTTP/解析皆可归于此）。"""
def fetch(url, timeout=12, retries=2, retry_interval=5, headers=None, params=None, method='GET', json_body=None):
    """带重试的 HTTP 抓取。网络异常与 5xx 均重试，4xx 不重试。"""
    hdrs = dict(BASE_HEADERS)
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            if method == 'POST':
                r = requests.post(url, headers=hdrs, params=params, json=json_body, timeout=timeout)
            else:
                r = requests.get(url, headers=hdrs, params=params, timeout=timeout)
            if r.status_code >= 500:
                raise FetchError(f'HTTP {r.status_code}')
            r.raise_for_status()
            r.encoding = r.apparent_encoding or 'utf-8'
            return r
        except FetchError:
            raise
        except requests.HTTPError as e:
            raise FetchError(f"HTTP {e.response.status_code if e.response else '?'}") from e
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_interval)
    if last_err:
        raise FetchError(f'{type(last_err).__name__}: {str(last_err)[:120]}')
    raise FetchError('未知抓取错误')
_TAG_RE = re.compile('<[^>]+>')
_WS_RE = re.compile('\\s+')
_PROMO_MARK = '欢迎关注'
def clean_text(s, max_len=None):
    """清洗任意来源文本：HTML 反转义→去标签→压空白→去推广尾巴→截断。"""
    if not s:
        return ''
    else:
        s = htmllib.unescape(str(s))
        if '<' in s and '>' in s:
                s = _TAG_RE.sub(' ', s)
        s = _WS_RE.sub(' ', s).strip()
        idx = s.find(_PROMO_MARK)
        if idx > 10:
            s = s[:idx].rstrip(' #｜|，,。；;')
        if max_len and len(s) > max_len:
                s = s[:max_len - 1] + '…'
        return s
def to_local_dt(time_struct_or_dt, default=None):
    """feedparser 的 struct_time / API 的 unix 秒 → 本地 datetime。"""
    if time_struct_or_dt is None:
        return default
    else:
        try:
            if isinstance(time_struct_or_dt, datetime):
                if time_struct_or_dt.tzinfo:
                    return time_struct_or_dt.astimezone()
                else:
                    return time_struct_or_dt
            else:
                ts = time.mktime(time_struct_or_dt)
                return datetime.fromtimestamp(ts)
        except (OverflowError, OSError, ValueError, TypeError):
            return default
def ts_to_local_dt(unix_seconds, default=None):
    """unix 秒时间戳 → 本地 datetime。"""
    try:
        v = int(unix_seconds)
        if v <= 0:
            return default
        return datetime.fromtimestamp(v)
    except (OverflowError, OSError, ValueError, TypeError):
        return default