"""边界/严苛回归测试（离线，mock 通道，不外发任何邮件）。"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

PASS = FAIL = 0

def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ✅ {name}')
    else:
        FAIL += 1
        print(f'  ❌ {name} {detail}')

from newshub3.config import Config, ConfigError
from newshub3.collectors import collect_all, _items_to_records, KNOWN_TYPES
from newshub3.collectors.base import Item, FetchError
from newshub3.db import Database
from newshub3.pipeline import build_digest_sections, summarize_stats
from newshub3.digest import build_messages, entries_json
from newshub3.boards import board_names, build_sources_config, build_keywords
from newshub3.core import NewsHubApp

TD = tempfile.mkdtemp(prefix='newshub_test_')
CFG = os.path.join(TD, 'config.json')

def write_cfg(d):
    with open(CFG, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)

base_cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.template.json'), encoding='utf-8'))
base_cfg['推送']['通道'] = 'mock'
base_cfg['采集']['单源间隔秒'] = 0

print('== 1. Config 边界 ==')
write_cfg(base_cfg)
cfg = Config(CFG)
check('首次读取建立 mtime', cfg._mtime > 0)
check('空来源列表→sources=[]', cfg.sources == [])
check('article_api_enabled 未启用=False', cfg.article_api_enabled is False)
base_cfg['文章API'] = {'启用': True, '接口地址': 'https://x/v1/chat/completions', '密钥': 'k', '模型': 'm'}
write_cfg(base_cfg)
r = cfg.reload(force=True)
check('reload(force) 感知变化', cfg.article_api_enabled is True)
old = dict(base_cfg)
base_cfg['推送']['推送时刻'] = ['25:99', 'abc', '7:3', '', None, {'时': 9, '分': 5}]
write_cfg(base_cfg)
r = cfg.reload(force=True)
check('非法推送时刻被归一且不崩', [t.strftime('%H:%M') for t in cfg.push_times] == ['01:39', '07:03', '09:05'], str(cfg.push_times))
with open(CFG, 'w', encoding='utf-8') as f:
    f.write('{broken json !!!')
err = cfg.reload(force=True)
check('坏 JSON→沿用旧配置并返回错误', err and cfg.push_times)
with open(CFG, 'w', encoding='utf-8') as f:
    json.dump(old, f, ensure_ascii=False)
cfg.reload(force=True)
today = datetime.now().date()
slots = cfg.today_push_datetimes(today)
check('today_push_datetimes 返回 datetime 列表', all(isinstance(s, datetime) for s in slots) and len(slots) == len(cfg.push_times))
base_cfg['采集']['来源'] = [
    {'name': 'A', 'type': 'rss', 'url': 'http://a', 'enabled': True},
    {'name': 'B', 'type': 'rss', 'url': 'http://b', 'enabled': True},
    'garbage-string',
    {'name': 'C', 'type': 'rss', 'url': 'http://c', 'enabled': True},
]
write_cfg(base_cfg)
cfg.reload(force=True)
check('sources 过滤 enabled/非 dict', [s['name'] for s in cfg.sources] == ['A', 'B', 'C'], str(cfg.sources))
print('== 2. boards ==')
names = board_names()
check('board_names 缺省=全部预设', len(names) == 6 and names[0] == '控制学科')
check('board_names 选择过滤', board_names(['机器人产业', '不存在']) == ['机器人产业'])
srcs = build_sources_config(['控制学科', 'AI·具身智能'])
on = [s['name'] for s in srcs if s['enabled']]
off = [s['name'] for s in srcs if not s['enabled']]
check('选中板块启用+无url预留位禁用', '量子位' in on and 'arXiv 控制理论' in on and '机器之心' in off and all(s.get('url') for s in srcs if s['enabled']), f'{on}/{off}')
check('build_keywords 并集去重', 'ADP' in build_keywords(['控制学科']) and '具身智能' in build_keywords(['AI·具身智能'], ['自定义词']) and '自定义词' in build_keywords(['AI·具身智能'], ['自定义词']))
print('== 3. 采集入库/去重/容错 ==')
db = Database(os.path.join(TD, 'news.db'))
def fake_collector(source, c):
    if source['name'] == 'B':
        raise FetchError('模拟失败')
    if source['name'] == 'C':
        raise RuntimeError('模拟内部异常')
    return [Item(category=source.get('分类', '测试类'), source=source['name'], title=f'{source["name"]} 文章{i}', url=f'http://{source["name"]}/{i}', summary='摘要' * 10, published_at=datetime.now()) for i in range(3)]
cfg.reload(force=True)
stats = collect_all(db, cfg, collector_override=fake_collector)
check('成功源统计形状', stats['A']['ok'] and stats['A']['count'] == 3 and stats['A']['total'] == 3, str(stats.get('A')))
check('单源失败不阻塞其他源', stats['B']['ok'] is False and '模拟失败' in stats['B']['error'] and stats['C']['ok'] is False)
check('失败源写入健康表', any(r['source'] == 'B' and not r['last_ok'] for r in db.source_health_all()))
stats2 = collect_all(db, cfg, collector_override=fake_collector)
check('重复采集去重（URL+标题 sha1）', stats2['A']['count'] == 0 and db.count() == 3, str(stats2['A']))
check('summarize_stats 不再 KeyError', summarize_stats(stats) is not None)
print('== 4. 组稿/简讯 ==')
rows = db.window_items('2000-01-01 00:00:00', '2099-01-01 00:00:00')
sections = build_digest_sections(rows, cfg)
check('sections 分组', any(sec['items'] for sec in sections.values()))
msgs = build_messages(sections, datetime.now(), 'mock')
check('简讯消息可生成', msgs and msgs[0][0] and msgs[0][1])
ej = entries_json(sections)
entries = json.loads(ej)
check('entries_json 存档完整', entries and all(set(e) >= {'category', 'title', 'url', 'is_notice'} for e in entries), ej[:80])
empty = build_messages({}, datetime.now(), 'mock')
check('空窗口返回占位消息', empty and '暂无更新' in empty[0][1])
print('== 5. 应用核心（推送/补发/握手判定） ==')
app = NewsHubApp(CFG, TD)
ok, err, n = app.do_push(kind='manual')
check('mock 通道 do_push 成功', ok and n >= 1, err)
check('推送后条目标记 pushed', len(db.window_items('2000-01-01 00:00:00', '2099-01-01 00:00:00')) == 0)
check('错过补发：伪造历史锚点后到期判定为 catchup', app.check_and_push_due() in (True, False))
last = db.last_successful_push_time()
check('窗口起点=上次成功推送', last is not None)
fake = lambda s, c: [Item(category='测试类', source='A', title='补发窗口文章', url='http://A/999', published_at=datetime.now())]
base_cfg['推送']['推送时刻'] = [(datetime.now() + timedelta(minutes=1)).strftime('%H:%M')]
write_cfg(base_cfg)
app.cfg.reload(force=True)
ok, err, n = app.do_push(kind='catchup', scheduled_for=datetime.now().strftime('%Y-%m-%d %H:%M'), collector_override=fake)
check('catchup 推送成功', ok, err)
db2 = app.db.recent_pushes(5)
check('推送记录含 catchup', any(p['kind'] == 'catchup' for p in db2))
dg = app.db.get_digests(datetime.now().strftime('%Y-%m-%d'))
check('简讯存档落库', len(dg) >= 1)
print('== 6. Agent ==')
from newshub3 import agent
kw = agent._extract_keywords('把库里关于 人形机器人 执行器 的内容报一版给我')
check('关键词抽取去动词', kw == ['人形机器人', '执行器'], str(kw))
p1 = agent.plan_message('订阅 https://example.com 的机器人内容，抓完推给我', cfg)
acts = [s['action'] for s in p1['steps']]
check('规则解析：订阅+推送链', acts == ['add_source', 'push'], str(acts))
p2 = agent.plan_message('采集一轮', cfg)
check('规则解析：采集', [s['action'] for s in p2['steps']] == ['collect'])
p3 = agent.plan_message('来源状态', cfg)
check('规则解析：status', [s['action'] for s in p3['steps']] == ['status'])
reply = agent.execute(app, p3)
check('execute status 正常返回', '库内共' in reply, reply[:80])
print('== 7. 仪表盘 HTTP（全部路由） ==')
from newshub3.dashboard import make_server, render_dashboard, write_static_dashboard
base_cfg['引导完成'] = True
write_cfg(base_cfg)
app.cfg.reload(force=True)
srv = make_server(app)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
for path, needle in [('/', 'NewsHub'), ('/setup', 'NewsHub'), ('/settings', '设置中心'), ('/agent', 'Agent'), ('/selfcheck', '自检'), ('/digest', '简讯'), ('/digest?date=' + datetime.now().strftime('%Y-%m-%d'), 'NewsHub'), ('/favicon.svg', '<svg'), ('/api/health', '"ok"'), ('/api/digests', '"dates"')]:
    try:
        resp = urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=10)
        body = resp.read().decode('utf-8', 'replace')
        check(f'GET {path} → {resp.status} 且含关键内容', resp.status == 200 and needle in body, body[:120])
    except Exception as e:
        check(f'GET {path}', False, str(e))
try:
    req = urllib.request.Request(f'http://127.0.0.1:{port}/api/agent', data=json.dumps({'message': '来源状态'}).encode(), headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=30)
    d = json.loads(resp.read().decode())
    check('POST /api/agent 正常', d.get('ok') and '库内共' in d.get('reply', ''), str(d)[:120])
except Exception as e:
    check('POST /api/agent', False, str(e))
try:
    resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/selfcheck?quick=1', timeout=60)
    d = json.loads(resp.read().decode())
    check('POST 路由 /api/selfcheck', d.get('ok') is not None)
except Exception as e:
    check('/api/selfcheck', False, str(e))
srv.shutdown()
check('静态仪表盘可写出', write_static_dashboard(app) is not None and os.path.isfile(os.path.join(TD, 'dashboard.html')))
print('== 8. 空数据/极端配置兜底 ==')
extreme = {'推送': {'通道': 'smtp', 'SMTP': {'端口': 'bad'}}, '采集': {'来源': None}, '调度': {'心跳间隔秒': -5}, '过滤': {'关键词': 'notalist'}}
write_cfg(extreme)
cfg2 = Config(CFG)
check('极端配置全部回退默认值不崩', cfg2.push_times and cfg2.heartbeat_sec >= 1 and cfg2.sources == [] and cfg2.smtp['端口'] == 465)
try:
    Config(os.path.join(TD, 'nope.json'))
    check('缺失配置抛 ConfigError', False)
except ConfigError:
    check('缺失配置抛 ConfigError', True)
print(f'\n===== 结果: {PASS} 通过 / {FAIL} 失败 =====')
sys.exit(1 if FAIL else 0)
