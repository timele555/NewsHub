"""pipeline.py —— 过滤、评分、分组、排序。

窗口口径：上次推送成功时刻 → 本次推送时刻（db.window_items 保证未推送的
漏网条目跨窗口也会进下一次简讯，不重不漏）。

评分：score = 来源权重 × 时间新鲜度 × 关键词系数
- 命中 k 个关键词：×(1 + 关键词加权系数×k)
- 未命中：×未命中惩罚系数（strict 模式下直接剔除）
- 每类 Top N：先取命中条目，不足时用高分未命中条目补足（boost 模式）
"""
import logging
from datetime import datetime
from .db import now_str
log = logging.getLogger('newshub3.pipeline')
def keyword_hits(text, keywords):
    """标题＋摘要里的关键词命中列表（不区分大小写）。"""
    t = (text or '').lower()
    out = []
    for k in keywords:
        kl = k.lower()
        if kl in t:
            out.append(kl)
    return out
def score_item(item, cfg, now=None):
    """单条评分。item 为 db 行 dict，附带 _hits 字段。"""
    now = now or datetime.now()
    pub = item.get('published_at') or item.get('collected_at') or now_str()
    try:
        dt = datetime.strptime(pub, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        dt = now
    age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    freshness = 0.5 ** (age_hours / cfg.halflife_hours)
    weight = cfg.source_weight(item.get('source', ''))
    hits = keyword_hits(f"{item.get('title', '')} {item.get('summary', '')}", cfg.keywords)
    item['_hits'] = hits
    s = weight * freshness
    if hits:
        s *= 1 + cfg.keyword_boost * len(hits)
    else:
        s *= cfg.miss_penalty
    item['_score'] = round(s, 4)
    item['_freshness'] = round(freshness, 4)
    return item
def build_digest_sections(items, cfg, now=None):
    """窗口内未推送条目 → {分类: {"items": [...], "notice_sources": [...]}}。

    - 条目按分数降序；每类先取关键词命中，不足 Top N 用未命中补足（boost 模式）；
    - strict 模式未命中直接剔除；
    - 财新等 is_notice 条目不占 Top N 名额，只归并为该类的"仅提示"来源行。
    """
    now = now or datetime.now()
    sections = {}
    for it in items:
        score_item(it, cfg, now)
        if it.get('is_notice'):
            continue
        if cfg.filter_mode == 'strict' and not it['_hits']:
            continue
        sections.setdefault(it.get('category', '未分类'), []).append(it)
    out = {}
    for cat, lst in sections.items():
        n_top = cfg.category_limits.get(cat, cfg.top_per_category)
        hit_items = sorted([x for x in lst if x['_hits']], key=lambda x: x['_score'], reverse=True)
        miss_items = sorted([x for x in lst if not x['_hits']], key=lambda x: x['_score'], reverse=True)
        picked = hit_items[:n_top]
        picked += miss_items[:max(0, n_top - len(picked))]
        out[cat] = {'items': picked, 'notice_sources': []}
    total_limit = getattr(cfg, 'digest_total_limit', 0)
    if total_limit:
        pool = [(it, cat) for cat, sec in out.items() for it in sec['items']]
        pool.sort(key=lambda x: (x[0]['_score'], x[0].get('published_at') or ''), reverse=True)
        keep_ids = {id(it) for it, _ in pool[:total_limit]}
        out = {cat: {'items': [it for it in sec['items'] if id(it) in keep_ids], 'notice_sources': sec['notice_sources']} for cat, sec in out.items()}
        out = {c: s for c, s in out.items() if s['items'] or s['notice_sources']}
    notice_srcs = {}
    for it in items:
        if it.get('is_notice'):
            notice_srcs.setdefault(it.get('category', '未分类'), set()).add(it.get('source'))
    for cat, srcs in notice_srcs.items():
        out.setdefault(cat, {'items': [], 'notice_sources': []})
        out[cat]['notice_sources'] = sorted(srcs)
    order = {'电子科技': 0, '机器人产业': 1, '财经科技/生活': 2}
    return {k: out[k] for k in sorted(out, key=lambda c: (order.get(c, 9), c))}
def summarize_stats(stats):
    """采集统计 → 「今日未更新来源」行文本（为空返回 None）。"""
    bad = []
    for name, s in stats.items():
        if (not s['ok']) and s.get('total', 0) == 0:
            reason = s.get('error') or '无更新'
            bad.append(f'{name}（{reason}）')
    return '、'.join(bad) if bad else None
