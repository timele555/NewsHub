"""boards.py —— V2 通用板块目录与来源注册表。\n\n\"板块\"= 内容主题 = 关键词集合 + 一组信息源。新手引导勾选板块，即可生成\nconfig.json 的 采集.来源 与 过滤.关键词，无需手写配置；自定义板块在仪表盘\n设置页编辑即可扩展（来源 type 见 collectors.__init__.KNOWN_TYPES）。\n"""
SOURCE_REGISTRY = [{'name': 'arXiv 控制理论', 'board': '控制学科', 'type': 'rss', 'weight': 1.5, 'url': 'https://export.arxiv.org/api/query?search_query=cat:cs.SY+OR+cat:eess.SY&sortBy=lastUpdatedDate&sortOrder=descending&max_results=30', '备注': '✅ arXiv 系统/控制：ADP/LQR/SMC/滑模/反步/MPC 等'}, {'name': 'arXiv 机器人学习', 'board': '控制学科', 'type': 'rss', 'weight': 1.4, 'url': 'https://export.arxiv.org/api/query?search_query=cat:cs.RO&sortBy=lastUpdatedDate&sortOrder=descending&max_results=30', '备注': '✅ arXiv 机器人：VLA/世界模型/学习控制/强化学习'}, {'name': '量子位', 'board': 'AI·具身智能', 'type': 'rss', 'weight': 1.2, 'url': 'https://www.qbitai.com/feed', '备注': '✅ 官方RSS'}, {'name': '智东西', 'board': 'AI·具身智能', 'type': 'html_zhidx', 'weight': 1.2, 'url': 'https://zhidx.com', '备注': '✅ 首页解析'}, {'name': '智源社区', 'board': 'AI·具身智能', 'type': 'html_baai', 'weight': 1.1, 'url': 'https://hub.baai.ac.cn', '备注': '✅ 内嵌数据解析'}, {'name': 'HuggingFace 论文', 'board': 'AI·具身智能', 'type': 'html_hf', 'weight': 1.1, 'url': 'https://huggingface.co/papers', '备注': '⚠️ 需外网,失败仅记录'}, {'name': 'IEEE Spectrum 机器人', 'board': '机器人产业', 'type': 'rss', 'weight': 1.2, 'url': 'https://spectrum.ieee.org/feeds/topic/robotics.rss', '备注': '✅ 官方RSS'}, {'name': 'The Robot Report', 'board': '机器人产业', 'type': 'rss', 'weight': 1.0, 'url': 'https://www.therobotreport.com/feed/', '备注': '⚠️ 站点反爬但RSS可用'}, {'name': '42号车库', 'board': '智能驾驶', 'type': 'html_42how', 'weight': 1.0, 'url': 'https://www.42how.com', '备注': '✅ 首页锚点,条目少属正常'}, {'name': '虎嗅', 'board': '财经科技', 'type': 'api_huxiu', 'weight': 0.7, 'url': 'https://api-article.huxiu.com/web/article/articleList', '备注': '✅ 官方web接口'}, {'name': '华尔街见闻', 'board': '财经科技', 'type': 'api_wscn', 'weight': 0.7, 'url': 'https://api-one.wallstcn.com/apiv1/content/lives', '备注': '✅ 公开快讯接口'}, {'name': '财新', 'board': '财经科技', 'type': 'notice_caixin', 'weight': 0.7, 'url': 'https://www.caixin.com', '备注': '🎓 付费源,仅提示有更新'}, {'name': '少数派', 'board': '数码生活', 'type': 'rss', 'weight': 0.8, 'url': 'https://sspai.com/feed', '备注': '✅ 官方RSS'}, {'name': '爱范儿', 'board': '数码生活', 'type': 'rss', 'weight': 0.8, 'url': 'https://www.ifanr.com/feed', '备注': '✅ 官方RSS'}, {'name': '机器之心', 'board': 'AI·具身智能', 'type': 'custom_rss', 'weight': 1.3, 'url': '', '备注': '【预留】填 RSSHub 地址后启用'}, {'name': '36氪', 'board': '财经科技', 'type': 'custom_rss', 'weight': 0.9, 'url': '', '备注': '【预留】填 RSSHub 地址后启用'}]
BOARD_PRESETS = [{'name': '控制学科', 'icon': '🎛️', 'desc': 'ADP · LQR · PID · FLC · SMC · BSC · MPC · 滑模 · 反步 · VLA · 世界模型', '关键词': ['ADP', 'LQR', 'PID', 'FLC', 'SMC', 'BSC', 'MPC', '滑模', '反步', '自适应动态规划', '模糊控制', '预测控制', '强化学习', 'VLA', '世界模型']}, {'name': 'AI·具身智能', 'icon': '🤖', 'desc': '大模型 · 具身智能 · 机器人 · Agent · 芯片', '关键词': ['具身智能', '机器人', '大模型', 'Agent', '芯片', '智元', '宇树']}, {'name': '机器人产业', 'icon': '🏭', 'desc': '人形机器人 · 执行器 · 产业动态', '关键词': ['机器人', '人形机器人', '执行器', '关节', '减速器']}, {'name': '智能驾驶', 'icon': '🚗', 'desc': '智驾 · 自动驾驶 · 智能汽车', '关键词': ['智驾', '自动驾驶', '智能汽车', '辅助驾驶']}, {'name': '财经科技', 'icon': '📈', 'desc': '宏观 · 市场 · 融资财报（默认降量）', '关键词': ['融资', '财报', 'IPO', '宏观']}, {'name': '数码生活', 'icon': '🧩', 'desc': '效率工具 · 数码 · 应用', '关键词': ['效率工具', '数码', 'App', '开源']}]
def board_names(preset_names=None):
    """已选板块名列表（缺省=全部预设）。"""
    if preset_names is None:
        return names
def build_sources_config(selected_boards, custom_sources=None):
    """根据勾选的板块生成 config.采集.来源 列表。\n\n    - 选中板块 → 该板块全部来源 enabled=true；\n    - 未选中板块 → 来源保留但 enabled=false（随时可在设置页重新勾选）；\n    - custom_rss 预留位（无 url）恒为 disabled；\n    - custom_sources 允许用户在设置页添加自定义来源（dict 列表，原样并入）。\n    """
    selected = set(selected_boards or [])
    out = []
    for s in SOURCE_REGISTRY:
        out.append(entry)
    for extra in custom_sources or []:
        e = dict(extra)
        e.setdefault('enabled', True)
        out.append(e)
    return out
def build_keywords(selected_boards, extra_keywords=None):
    """选中板块关键词并集 + 用户自定义关键词（去重保序）。"""
    selected = set(selected_boards or [])
    out = []
    for b in BOARD_PRESETS:
        if b['name'] in selected:
            for k in b['关键词']:
                if k not in out:
                    out.append(k)
    for k in extra_keywords or []:
        k = str(k).strip()
        if k and k not in out:
                out.append(k)
    return out