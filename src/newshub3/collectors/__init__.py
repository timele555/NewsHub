"""collectors —— 采集调度：按 config 的来源清单逐个采集并入库。"""
import logging
import time
import traceback
from .base import Item, FetchError
from .rss_collector import collect_rss
from .html_sources import collect_zhidx, collect_baai, collect_hf, collect_42how, collect_caixin, collect_generic
from .api_sources import collect_huxiu, collect_wscn
log = logging.getLogger('newshub3.collect')
def _run_one(source, cfg):
    """执行单个源的采集函数，返回 Item 列表。未知类型/空 custom_rss 抛错。"""
    ctype = str(source.get('type', '')).strip()
    fn = _COLLECTORS.get(ctype)
    if fn is None:
        raise FetchError(f'未知来源类型 {ctype}（可选: {KNOWN_TYPES}）')
    else:
        if ctype == 'custom_rss':
                raise FetchError('custom_rss 未填写第三方 RSS 地址')
        return fn(source, cfg)
def _items_to_records(items):
    """Item → 可插入 dict（时间转 ISO 字符串）。"""
    out = []
    for it in items:
        pass
    return out
def collect_all(db, cfg, sources=None, collector_override=None):
    """采集全部启用来源并入库。collector_override 供测试注入假采集器。\n\n    返回统计 {source: {\"ok\": bool, \"count\": int, \"error\": str}}。\n    约束：单源之间间隔 ≥ cfg.source_gap（默认3秒）；任何单源失败不阻塞其他源。\n    """
    stats = {}
    srcs = sources if sources is not None else cfg.sources
    for idx, source in enumerate(srcs):
        name = source.get('name', f'来源{idx}')
        if idx > 0:
            time.sleep(cfg.source_gap)
        t0 = time.time()
        try:
            if collector_override is not None:
                items = collector_override(source, cfg)
            else:
                items = _run_one(source, cfg)
            n_new = 0
            for rec in _items_to_records(items):
                    n_new += 1
        except FetchError as e:
            msg = str(e)
            db.update_source_health(name, ok=False, error=msg)
            log.warning('来源[%s] 采集失败: %s', name, msg)
        except Exception as e:
            msg = f'内部异常: {type(e).__name__}: {e}'
            db.update_source_health(name, ok=False, error=msg)
    return stats