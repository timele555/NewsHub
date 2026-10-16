"""config.py —— 配置加载与校验。\n\n设计要点：\n- config.json 是唯一事实来源，每次心跳都重新读取，改完 1 分钟内生效、无需重启；\n- 读取失败（JSON 语法错误等）时保留上一份有效配置并告警，程序不崩；\n- 所有字段带默认值，用户删掉部分字段也能跑。\n"""
import json
import os
import threading
from datetime import datetime, time as dtime
class ConfigError(Exception):
    """配置致命错误（文件不存在/无法解析）。"""
    pass
DEFAULT_PUSH_TIMES = ['07:30', '21:30']
DEFAULT_KEYWORDS = ['FOC', '无刷电机', '机器人', '具身智能', '机械臂', '芯片', '智驾', 'EDA', 'MCU', '融资', '财报']
def _get(d, key, default):
    """安全取值：字段缺失或类型不对时回退默认值。"""
    v = d.get(key, default)
    if v is None:
        return default
    else:
        return v
class Config:
    """线程安全的配置持有者。心跳线程定期 reload()，其他线程随时读。"""
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._mtime = 0.0
        if not os.path.exists(self.path):
            raise ConfigError(f'配置文件不存在: {self.path}')
        else:
            self._cfg = {}
            self._read(raise_on_error=True)
    def reload(self, force=False):
        """文件 mtime 变化时重读；解析失败沿用旧配置并返回错误信息（不抛异常）。"""
        try:
            m = os.path.getmtime(self.path)
        except OSError:
                return
    def _read(self, raise_on_error, mtime=None):
        try:
            with open(self.path, 'r', encoding='utf-8-sig') as f:
                text = f.read()
            cfg = json.loads(text)
            if not isinstance(cfg, dict):
                raise ValueError('顶层必须是 JSON 对象')
        except Exception as e:
            err = f'配置文件解析失败，沿用上次有效配置: {e}'
            if raise_on_error and (not self._cfg):
                raise ConfigError(err) from e
            else:
                return err
        self._cfg = cfg
    @property
    def raw(self):
        with self._lock:
            return self._cfg
    @property
    def push(self):
        return self.raw.get('推送', {})
    @property
    def channel_type(self):
        return str(_get(self.push, '通道', 'mock')).strip().lower() or 'mock'
    @property
    def push_times(self):
        """解析推送时刻为 datetime.time 列表；非法项跳过并尽量归一（如 \'7:3\'）。"""
        out, seen = [], set()
        for t in _get(self.push, '推送时刻', DEFAULT_PUSH_TIMES):
            try:
                if isinstance(t, str):
                    hh, mm = t.strip().split(':')
                    tm = dtime(int(hh) % 24, int(mm) % 60)
                elif isinstance(t, dict):
                    tm = dtime(int(t.get('时', 7)) % 24, int(t.get('分', 30)) % 60)
                else:
                    continue
                if tm not in seen:
                    seen.add(tm)
                    out.append(tm)
            except (ValueError, AttributeError):
                continue
        return out or [dtime(7, 30), dtime(21, 30)]
    @property
    def top_per_category(self):
        try:
            return max(1, min(20, int(_get(self.push, '每类条数上限', 5))))
        except (TypeError, ValueError):
            return 5
    @property
    def category_limits(self):
        """每类条数覆盖：{\"分类名\": N}，优先于全局 每类条数上限。"""
        d = self.push.get('每类条数覆盖', {}) or {}
        out = {}
        if isinstance(d, dict):
            for k, v in d.items():
                try:
                    out[str(k)] = max(0, min(20, int(v)))
                except (TypeError, ValueError):
                    pass
        return out
    @property
    def digest_style(self):
        """简讯行样式: title_url=标题+网址(轻量) / title_summary_url=标题+摘要+网址。"""
        s = str(_get(self.push, '简讯样式', 'title_url')).lower()
        return s if s in ('title_url', 'title_summary_url') else 'title_url'
    @property
    def digest_total_limit(self):
        """单封简讯总条数上限（跨分类合计），0=不限制。"""
        try:
            pass
        except (TypeError, ValueError):
            return 12
    @property
    def wall_limit(self):
        """仪表盘标题墙每日精选条数（默认 30，建议 20-30）。"""
        try:
            pass
        except (TypeError, ValueError):
            return 30
    @property
    def send_timeout(self):
        try:
            pass
        except (TypeError, ValueError):
            return 15
    @property
    def webhook(self):
        v = str(self.push.get('企业微信_Webhook', '')).strip()
        if '在这里粘贴' in v or 'xxxx' in v or not v.startswith('http'):
            return ''
        return v
    @property
    def serverchan_key(self):
        return str(self.push.get('Server酱_SendKey', '')).strip()
    @property
    def bark_url(self):
        v = str(self.push.get('Bark_推送URL', '')).strip()
        if '你的Key' in v or not v.startswith('http'):
            return ''
        else:
            return v
    @property
    def smtp(self):
        d = self.push.get('SMTP', {}) or {}
    @property
    def filter_cfg(self):
        return self.raw.get('过滤', {})
    @property
    def keywords(self):
        kw = _get(self.filter_cfg, '关键词', DEFAULT_KEYWORDS)
        out = []
        for k in kw if isinstance(kw, list) else []:
            k = str(k).strip()
            if k:
                out.append(k)
        return out or DEFAULT_KEYWORDS
    @property
    def filter_mode(self):
        m = str(_get(self.filter_cfg, '模式', 'boost')).lower()
        return m if m in ('boost', 'strict') else 'boost'
    @property
    def halflife_hours(self):
        try:
            pass
        except (TypeError, ValueError):
            return 12.0
    @property
    def keyword_boost(self):
        try:
            pass
        except (TypeError, ValueError):
            return 0.4
    @property
    def miss_penalty(self):
        try:
            pass
        except (TypeError, ValueError):
            return 0.4
    def source_weight(self, source_name):
        w = self.filter_cfg.get('来源权重', {}) or {}
        try:
            v = w.get(source_name, w.get('默认', 1.0))
            return max(0.1, float(v))
        except (TypeError, ValueError):
            return 1.0
    @property
    def collect_cfg(self):
        return self.raw.get('采集', {})
    @property
    def sources(self):
        """返回启用中的来源列表（dict 原样，仅过滤 enabled）。"""
        out = []
        for s in _get(self.collect_cfg, '来源', []):
                            out.append(s)
        return out
    def all_sources(self):
        return [s for s in _get(self.collect_cfg, '来源', []) if isinstance(s, dict)]
    @property
    def http_timeout(self):
        try:
            pass
        except (TypeError, ValueError):
            return 12
    @property
    def retries(self):
        try:
            pass
        except (TypeError, ValueError):
            return 2
    @property
    def retry_interval(self):
        try:
            pass
        except (TypeError, ValueError):
            return 5
    @property
    def source_gap(self):
        """单源间隔≥3秒（限速约束）。显式填 0 仅建议测试环境使用。"""
        try:
            v = float(_get(self.collect_cfg, '单源间隔秒', 3))
        except (TypeError, ValueError):
            return 3.0
    @property
    def per_source_limit(self):
        try:
            pass
        except (TypeError, ValueError):
            return 30
    @property
    def summary_maxlen(self):
        try:
            pass
        except (TypeError, ValueError):
            return 80
    @property
    def heartbeat_sec(self):
        try:
            pass
        except (TypeError, ValueError):
            return 30
    @property
    def bg_collect_hours(self):
        try:
            pass
        except (TypeError, ValueError):
            return 3.0
    @property
    def push_retry_limit(self):
        try:
            pass
        except (TypeError, ValueError):
            return 3
    @property
    def net_retry_minutes(self):
        """无网络时握手重试间隔（分钟），恢复后自动补采集/补推。"""
        try:
            pass
        except (TypeError, ValueError):
            return 5
    @property
    def onboarded(self):
        """新手引导是否完成（false 时仪表盘自动跳转 /setup）。"""
        return bool(self.raw.get('引导完成', False))
    @property
    def catchup_enabled(self):
        """错过补发开关（推送段「错过补发」，默认开）。"""
        return bool(_get(self.push, '错过补发', True))
    @property
    def dashboard_port(self):
        try:
            pass
        except (TypeError, ValueError):
            return 8365
    @property
    def archive_days(self):
        """30 天滚动归档周期：过期条目/简讯瘦身仅留标题+链接（不清除）。"""
        v = self.raw.get('仪表盘', {})
        for key in ['归档天数', '条目保留天数']:
            try:
                if v.get(key) is not None:
                    pass
            except (TypeError, ValueError):
                pass
        return 30
    @property
    def auto_open_browser(self):
        """启动常驻时自动打开浏览器进仪表盘（默认关，桌面窗口模式无需此项）。"""
    @property
    def ui_mode(self):
        """常驻界面形态: window=桌面阅读窗口(默认) / browser=浏览器。"""
        return m if m in ('window', 'browser') else 'window'
    @property
    def article_api(self):
        return self.raw.get('文章API', {}) or {}
    @property
    def article_api_enabled(self):
        a = self.article_api
        if not bool(a.get('启用', False)):
            return False
    @property
    def article_api_limit(self):
        try:
            pass
        except (TypeError, ValueError):
            return 5
    def today_push_datetimes(self, day):
        """给定日期（datetime.date）→ 当天各推送时刻的 datetime 列表。"""
    def channel_ready(self):
        """当前通道凭证是否已填写（mock 恒为就绪）。"""
        t = self.channel_type
        if t == 'mock':
            return True
        else:
            if t == 'wecom':
                return bool(self.webhook)
            else:
                if t == 'serverchan':
                    return bool(self.serverchan_key)
                else:
                    if t == 'bark':
                        return bool(self.bark_url)
                    else:
                        if t == 'smtp':
                            s = self.smtp
                        else:
                            return False