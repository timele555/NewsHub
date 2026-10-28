"""agent.py —— 仪表盘内置 Agent：自然语言需求 → 抓取/推送工作流。\n\n两种理解模式（自动选择）：\n- LLM 模式：config「文章API」已启用时，把需求交给 OpenAI 兼容接口解析成\n  结构化动作（能理解复杂表述），失败自动回退规则模式；\n- 规则模式：零依赖的本地意图解析（URL 识别 + 动词/关键词匹配），\n  覆盖常用句式，无需任何外部服务。\n\n动作集（execute 按顺序执行）：\n  status      汇报来源健康与库内条数\n  add_source  把新站点写入 config（html_generic 自适应采集）并立即采集一轮\n  collect     采集全部已启用来源\n  push        采集 + 推送当前窗口简讯到绑定邮箱\n  push_topic  按关键词在库内筛选近 48 小时条目，即时报送一版专题简讯\n  disable     停用某个来源（按名称模糊匹配）\n  help        用法说明\n\n安全边界：Agent 只操作本地 config/news.db 与已配置的推送通道；\n不执行任意代码、不读写任务之外的文件。\n"""
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
import requests
log = logging.getLogger('newshub3.agent')
URL_RE = re.compile('https?://[^\\s，。、\\\"\'<>()】\\]]+')
_PUSH_WORDS = ('推送', '发送', '发我', '发到邮箱', '推给我', '推送给我', '报送', '发一版', '推一版', '立即推送', '现在推送')
_ADD_WORDS = ('订阅', '关注', '添加', '新增', '盯', '跟踪', '盯着', '加入')
_COLLECT_WORDS = ('抓取', '采集', '抓一下', '收一轮', '刷新一下')
_DISABLE_WORDS = ('停用', '禁用', '不要', '删除', '移除', '取消订阅', '取关')
_STATUS_WORDS = ('状态', '健康', '怎么样', '情况', '汇报', '诊断')
CATEGORY_HINTS = [('机器人', '机器人产业'), ('具身', 'AI·具身智能'), ('AI', 'AI·具身智能'), ('人工智能', 'AI·具身智能'), ('大模型', 'AI·具身智能'), ('智能驾驶', '智能驾驶'), ('自动驾驶', '智能驾驶'), ('智驾', '智能驾驶'), ('汽车', '智能驾驶'), ('车', '智能驾驶'), ('控制', '控制学科'), ('财经', '财经科技'), ('金融', '财经科技'), ('数码', '数码生活'), ('效率', '数码生活')]
LLM_SYSTEM_PROMPT = '你是 NewsHub 资讯聚合器的任务解析器。把用户的中文需求解析为一个 JSON 对象，只输出 JSON 本身。\n可用动作：\n- \"status\"：汇报来源健康\n- \"add_source\"：订阅新站点（字段 url 必填，name 可选默认域名，分类 可选）\n- \"collect\"：采集一轮全部来源\n- \"push\"：采集并把当前窗口简讯推送到绑定邮箱\n- \"push_topic\"：按 keywords 在本地库筛选近48小时条目，即时报送专题简讯（字段 keywords: [词]）\n- \"disable\"：停用来源（字段 source_name）\n- \"help\"：用法说明\n规则：\n1. 一次需求可链式多步时，输出 steps 数组按执行顺序排列，例如\"订阅 xxx 并推给我\" → steps=[{\"action\":\"add_source\",...},{\"action\":\"push\"}]。\n2. 无需多步时 steps 只含一项。只输出 {\"steps\":[...]}，不要任何解释文字。'
_NOISE_WORDS = ('把', '关于', '的', '内容', '一版', '库里', '给我', '我', '一下', '现在', '立即', '相关', '全部', '所有', '报', '来', '帮', '请', '近48小时', '今天', '推送', '发送')
def _extract_keywords(text):
    """去掉动词/助词后剩余的实质词（用于 push_topic）。"""
    t = text
    for v in _PUSH_WORDS + _ADD_WORDS + _COLLECT_WORDS + _DISABLE_WORDS + _STATUS_WORDS + _NOISE_WORDS:
        t = t.replace(v, ' ')
    words = re.split('[\\s，。、,.！!？?；;：:]+', t)
    out = []
    for w in words:
        w = w.strip()
        if len(w) < 2 or w.startswith('http') or w in out:
            continue
        out.append(w)
    return out
def _guess_category(text):
    for hint, cat in CATEGORY_HINTS:
        if hint in text:
            return cat
    return '自定义'
def _plan_rules(text):
    """规则模式：URL + 动词 → 动作序列。"""
    steps = []
    url_m = URL_RE.search(text)
    url = url_m.group(0).rstrip('.,;)，。；）') if url_m else ''
    wants_add = any((w in text for w in _ADD_WORDS))
    wants_push = any((w in text for w in _PUSH_WORDS))
    wants_collect = any((w in text for w in _COLLECT_WORDS))
    wants_disable = any((w in text for w in _DISABLE_WORDS))
    wants_status = any((w in text for w in _STATUS_WORDS))
    if url and (wants_add or wants_push or wants_collect):
        domain = urlparse(url).netloc.replace('www.', '')
        steps.append({'action': 'add_source', 'url': url, 'name': domain, '分类': _guess_category(domain), '备注': '🤖 Agent 添加'})
    if wants_disable and not url:
        steps.append({'action': 'disable', 'source_name': _best_source_name(text, None)})
    if not steps and wants_collect:
        steps.append({'action': 'collect'})
    if wants_push:
        if not steps or steps[0].get('action') != 'add_source':
            kws = _extract_keywords(text)
            if kws and not url:
                steps.append({'action': 'push_topic', 'keywords': kws[:5]})
            else:
                steps.append({'action': 'push'})
        else:
            steps.append({'action': 'push'})
    if not steps and wants_status:
        steps.append({'action': 'status'})
    if not steps:
        kws = _extract_keywords(text)
        if kws:
            steps.append({'action': 'push_topic', 'keywords': kws[:5]})
            return {'steps': steps}
        steps.append({'action': 'help'})
    return {'steps': steps}
def _plan_llm(text, cfg):
    """LLM 模式：复用「文章API」的 OpenAI 兼容接口解析需求；失败返回 None。"""
    a = cfg.article_api
    try:
        r = requests.post(a.get('接口地址', ''), headers={'Authorization': 'Bearer ' + a.get('密钥', ''), 'Content-Type': 'application/json'}, json={'model': a.get('模型', '') or 'deepseek-chat', 'temperature': 0, 'messages': [{'role': 'system', 'content': LLM_SYSTEM_PROMPT}, {'role': 'user', 'content': text}]}, timeout=max(10, int(a.get('超时秒', 30) or 30)))
        content = str(r.json()['choices'][0]['message']['content']).strip()
        m = re.search('\\{.*\\}', content, re.S)
        plan = json.loads(m.group(0) if m else content)
        steps = plan.get('steps')
        if isinstance(steps, list) and steps:
            return plan
        return None
    except Exception as e:
        log.info('Agent LLM 解析失败，回退规则模式: %s', str(e)[:120])
        return None
def plan_message(text, cfg):
    """需求文本 → {\"steps\":[...], \"mode\": \"llm\"/\"rules\"}。"""
    if cfg.article_api_enabled:
        plan = _plan_llm(text, cfg)
        if plan:
            plan['mode'] = 'llm'
            return plan
    plan = _plan_rules(text)
    plan['mode'] = 'rules'
    return plan
def _best_source_name(text, cfg_sources):
    """从需求里猜要停用的来源名：取除动词外最像名称的片段（执行时再模糊匹配）。"""
    kws = _extract_keywords(text)
    return kws[0] if kws else ''
def _write_source(app, step):
    """把新来源写入 config（同 URL 覆盖），返回 (来源dict, 是否新建)。"""
    import os
    url = str(step.get('url', '')).strip()
    if not url.startswith(('http://', 'https://')):
        raise ValueError('URL 不合法: ' + url[:80])
    name = str(step.get('name') or urlparse(url).netloc.replace('www.', ''))[:40] or '新来源'
    cat = str(step.get('分类') or '自定义')[:20]
    entry = {'name': name, '分类': cat, 'type': 'html_generic', 'url': url, 'enabled': True, '备注': str(step.get('备注') or '🤖 Agent 添加')}
    path = app.cfg.path
    with open(path, 'r', encoding='utf-8-sig') as f:
        disk = json.load(f)
    sources = disk.setdefault('采集', {}).setdefault('来源', [])
    exists = False
    for i, s in enumerate(sources):
        if str(s.get('url', '')).strip().rstrip('/') == url.rstrip('/') or s.get('name') == name and s.get('type') == 'html_generic':
            sources[i] = entry
            exists = True
            break
    if not exists:
        sources.append(entry)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(disk, f, ensure_ascii=False, indent=2)
    app.cfg.reload(force=True)
    return (entry, not exists)
def _do_status(app):
    health = app.db.source_health_all()
    ok = sum((1 for r in health if r['last_ok']))
    lines = [f'库内共 {app.db.count()} 条；来源 {ok}/{len(health)} 正常：']
    for r in sorted(health, key=lambda x: x['source']):
        state = '✅' if r['last_ok'] else '❌'
        err = '' if r['last_ok'] else f"（{(r['last_error'] or '')[:40]}）"
        lines.append(f"{state} {r['source']}：新增 {r['last_count'] or 0}{err}")
    return '\n'.join(lines)
def _do_disable(app, source_name):
    if not source_name:
        return '请说明要停用哪个来源（例如：停用 华尔街见闻）。'
    with open(app.cfg.path, 'r', encoding='utf-8-sig') as f:
        disk = json.load(f)
    sources = disk.setdefault('采集', {}).setdefault('来源', [])
    hit = None
    for s in sources:
        if source_name in str(s.get('name', '')) or str(s.get('name', '')) in source_name:
            hit = s
            break
    if not hit:
        avail = '、'.join((s.get('name', '?') for s in sources)) or '（无）'
        return f'没找到匹配「{source_name}」的来源。现有来源：{avail}'
    hit['enabled'] = False
    with open(app.cfg.path, 'w', encoding='utf-8') as f:
        json.dump(disk, f, ensure_ascii=False, indent=2)
    app.cfg.reload(force=True)
    return f"已停用「{hit['name']}」（30 秒内生效；重新启用可在设置页勾选或找 Agent）。"
def _do_push_topic(app, keywords):
    """库内近 48 小时、标题/摘要命中关键词的条目 → 即时专题简讯。"""
    from .pipeline import score_item
    since = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    rows = app.db.articles_for_dashboard(limit=500)
    picked = []
    for r in rows:
        ts = r.get('published_at') or r.get('collected_at') or ''
        if ts and ts < since:
            continue
        hay = (r.get('title', '') + ' ' + (r.get('summary') or '')).lower()
        if not any((kw.lower() in hay for kw in keywords)):
            continue
        score_item(r, app.cfg)
        picked.append(r)
    if not picked:
        return (False, f"近 48 小时没有命中关键词「{'、'.join(keywords)}」的条目，未发送。", 0)
    picked.sort(key=lambda r: (r['_score'], r.get('published_at') or ''), reverse=True)
    picked = picked[:15]
    lines = [f"[{r['category']}] {r['title']}\n  {r['url']}" for r in picked]
    body = f"关键词专题：{'、'.join(keywords)}\n命中 {len(picked)} 条（近48小时，按相关度）：\n\n" + '\n\n'.join(lines)
    title = f"【专题】{'、'.join(keywords[:3])} · {len(picked)} 条"
    try:
        channel = app._make_channel()
    except Exception as e:
        return (False, f'通道不可用：{e}', 0)
    ok, err = channel.send(title, body)
    app.db.record_push('agent-topic', 'success' if ok else 'failed', channel.name, '', '', len(picked), err)
    return (ok, f'专题简讯已发送（{len(picked)} 条）。' if ok else f'发送失败：{err}', len(picked))
def _step_add_source(app, step, logs):
    try:
        entry, created = _write_source(app, step)
    except Exception as e:
        logs.append(f'❌ 添加来源失败：{e}')
        return None
    verb = '已订阅' if created else '已更新'
    logs.append(f"➕ {verb}「{entry['name']}」（{entry['url']}，分类 {entry['分类']}），正在采集…")
    try:
        stats = app.run_collection(sources=[entry])
        s = stats.get(entry['name'], {})
        if s.get('ok'):
            logs.append(f"✅ 采集成功：{s.get('total', 0)} 条（新增 {s.get('count', 0)}）")
        else:
            logs.append(f"⚠️ 采集失败：{s.get('error', '未知')}")
    except Exception as e:
        logs.append(f'⚠️ 采集异常：{str(e)[:100]}')
    return entry
def execute(app, plan):
    """执行计划 → (reply文本, logs)。每步的执行结果都进 logs。"""
    logs = []
    steps = plan.get('steps') or []
    for step in steps:
        action = str(step.get('action', '')).lower()
        try:
            if action == 'add_source':
                _step_add_source(app, step, logs)
            elif action == 'collect':
                stats = app.run_collection()
                ok = sum((1 for s in stats.values() if s['ok']))
                logs.append(f"✅ 采集完成：{ok}/{len(stats)} 来源正常，新增 {sum((s['count'] for s in stats.values()))} 条")
            elif action == 'push':
                ok, err, n = app.do_push(kind='agent')
                logs.append(f"{'✅ 推送成功' if ok else '❌ 推送失败'}（{n} 条）" + (f'：{err[:80]}' if err else ''))
            elif action == 'push_topic':
                ok, msg, n = _do_push_topic(app, step.get('keywords') or [])
                logs.append(('✅ ' if ok else 'ℹ️ ') + msg)
            elif action == 'disable':
                logs.append(_do_disable(app, step.get('source_name', '')))
            elif action == 'status':
                logs.append(_do_status(app))
            elif action == 'help':
                logs.append(HELP_TEXT)
            else:
                logs.append(f'⚠️ 未知动作 {action}，已跳过')
        except Exception as e:
            logs.append(f'❌ {action} 执行失败：{str(e)[:120]}')
    return '\n'.join(logs)
HELP_TEXT = '可以这样对我说：\n· 「订阅 https://example.com 的机器人内容，抓完推给我」\n· 「把库里关于 人形机器人 的内容报一版给我」\n· 「采集一轮」「立即推送」「来源状态」「停用 华尔街见闻」\n（接入文章API 后我能理解更复杂的表述；未接入时用本地规则解析，以上句式最稳）'
