"""pipeline.py —— 过滤、评分、分组、排序。\n\n窗口口径：上次推送成功时刻 → 本次推送时刻（db.window_items 保证未推送的\n漏网条目跨窗口也会进下一次简讯，不重不漏）。\n\n评分：score = 来源权重 × 时间新鲜度 × 关键词系数\n- 命中 k 个关键词：×(1 + 关键词加权系数×k)\n- 未命中：×未命中惩罚系数（strict 模式下直接剔除）\n- 每类 Top N：先取命中条目，不足时用高分未命中条目补足（boost 模式）\n"""
import logging
from datetime import datetime
from .db import now_str
log = logging.getLogger('newshub3.pipeline')
def keyword_hits(text, keywords):
    """标题＋摘要里的关键词命中列表（不区分大小写）。"""
    t = (text or '').lower()
def score_item(item, cfg, now=None):
    """单条评分。item 为 db 行 dict，附带 _hits 字段。"""
    now = now or datetime.now()
    try:
        dt = datetime.strptime(pub, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        dt = now
    weight = cfg.source_weight(item.get('source', ''))
    item['_hits'] = hits
    s = weight * freshness
    if hits:
        pass
    else:
        s *= cfg.miss_penalty
    item['_score'] = round(s, 4)
    item['_freshness'] = round(freshness, 4)
    return item
def build_digest_sections(items, cfg, now=None):
    """窗口内未推送条目 → {分类: {\"items\": [...], \"notice_sources\": [...]}}。\n\n    - 条目按分数降序；每类先取关键词命中，不足 Top N 用未命中补足（boost 模式）；\n    - strict 模式未命中直接剔除；\n    - 财新等 is_notice 条目不占 Top N 名额，只归并为该类的\"仅提示\"来源行。\n    """
    now = now or datetime.now()
    sections = {}
    for it in items:
        score_item(it, cfg, now)
        if it.get('is_notice'):
            continue
        else:
            if cfg.filter_mode == 'strict' and (not it['_hits']):
                    continue
    out = {}
    for cat, lst in sections.items():
        n_top = cfg.category_limits.get(cat, cfg.top_per_category)
        picked = hit_items[:n_top]
    total_limit = getattr(cfg, 'digest_total_limit', 0)
    if total_limit:
        pass
    notice_srcs = {}
    for it in items:
        if it.get('is_notice'):
            pass
    for cat, srcs in notice_srcs.items():
        out.setdefault(cat, {'items': [], 'notice_sources': []})
        out[cat]['notice_sources'] = sorted(srcs)
    order = {'电子科技': 0, '机器人产业': 1, '财经科技/生活': 2}
def summarize_stats(stats):
    """采集统计 → 「今日未更新来源」行文本（为空返回 None）。"""
    bad = []
    for name, s in stats.items():
            reason = s.get('error') or '无更新'
    return '、'.join(bad) if bad else None