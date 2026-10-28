"""core.py —— 应用核心：采集 / 窗口汇总 / 推送 / 补发 判定。\n\n窗口语义（不重不漏的关键）：\n- 窗口起点 = 最近一次「成功推送」时刻（落库于 pushes 表）；\n- 窗口内条目 = 该起点之后采集、且尚未推送成功的条目；\n- 推送成功才把条目标记 pushed 并推进窗口起点；失败则窗口保持不动，下次重试。\n"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
import requests
from .collectors import collect_all
from .config import Config
from .db import Database, now_str
from .digest import build_messages, render_html, entries_json, write_md, slim_digest_files
from .llm import ArticleProcessor, enrich_items
from .pipeline import build_digest_sections, summarize_stats
from .push import create_channel, PushError
log = logging.getLogger('newshub3.core')
NET_PROBES = ('https://www.baidu.com', 'https://export.arxiv.org', 'https://www.qq.com')
def probe_network(timeout=3):
    """任一探测点可达即视为在线（stream=True 不下载正文）。"""
    for url in NET_PROBES:
        try:
            r = requests.get(url, timeout=timeout, stream=True)
            r.close()
            if r.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False
class Busy(Exception):
    """同一时刻已有采集/推送在进行。"""
def apply_onboarding(config_path, payload):
    """新手引导完成 → 把向导数据写回 config.json（引导完成=true）。

    payload 字段（均可选，缺省沿用现值）：
      板块: [板块名...]；自定义关键词: [str]；SMTP: {服务器,端口,账号,授权码,收件人}；
      推送时刻: ["08:00"]；文章API: {启用,接口地址,密钥,模型,只处理每类前N条}
    返回 (ok, err)。
    """
    import json
    from .boards import build_sources_config, build_keywords
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            cfg = json.load(f)
        boards = payload.get('板块') or []
        if not boards:
            return (False, '至少选择一个内容板块')
        smtp = payload.get('SMTP') or {}
        if not all([smtp.get('服务器'), smtp.get('账号'), smtp.get('授权码'), smtp.get('收件人')]):
            return (False, 'QQ 邮箱绑定信息不完整（服务器/账号/授权码/收件人）')
        cfg['采集']['来源'] = build_sources_config(boards)
        kw = build_keywords(boards, payload.get('自定义关键词'))
        if kw:
            cfg['过滤']['关键词'] = kw
        cfg['推送']['通道'] = 'smtp'
        cfg['推送']['SMTP'] = {'服务器': str(smtp['服务器']).strip(), '端口': int(smtp.get('端口', 465) or 465), '账号': str(smtp['账号']).strip(), '授权码': str(smtp['授权码']).strip(), '收件人': str(smtp['收件人']).strip()}
        times = payload.get('推送时刻') or ['08:00']
        cfg['推送']['推送时刻'] = [str(t) for t in times] or ['08:00']
        api = payload.get('文章API')
        if api and api.get('接口地址') and api.get('密钥'):
            cfg['文章API'] = {'启用': bool(api.get('启用', True)), '接口地址': str(api['接口地址']).strip(), '密钥': str(api['密钥']).strip(), '模型': str(api.get('模型', '')).strip(), '超时秒': 30, '只处理每类前N条': max(1, min(20, int(api.get('只处理每类前N条', 5) or 5)))}
        cfg['引导完成'] = True
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return (True, '')
    except Exception as e:
        return (False, f'{type(e).__name__}: {e}')
def apply_skip(config_path):
    """跳过引导：标记引导完成；来源为空时启用全部预设板块（邮箱可稍后在设置页绑定，未绑定时简讯只存档不发送）。"""
    import json
    from .boards import build_sources_config, board_names
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            cfg = json.load(f)
        srcs = cfg.setdefault('采集', {}).get('来源') or []
        if not any(isinstance(s, dict) and s.get('enabled') for s in srcs):
            cfg['采集']['来源'] = build_sources_config(board_names())
        cfg['引导完成'] = True
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return (True, '')
    except Exception as e:
        return (False, f'{type(e).__name__}: {e}')
class NewsHubApp:
    def __init__(self, config_path, data_dir):
        self.cfg = Config(config_path)
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.db = Database(os.path.join(data_dir, 'news.db'))
        self._work_lock = threading.Lock()
        self.last_stats = {}
        self.last_collect_at = None
        self._push_fail_streak = 0
        self.net_ok = None
        self._next_net_check = 0.0
    def ensure_network(self):
        """有网才干活。在线每 60 秒确认一次；离线按 cfg.net_retry_minutes 握手
        （默认 5 分钟），恢复瞬间由心跳自动补采集/补推。"""
        now = time.monotonic()
        if now < self._next_net_check:
            return bool(self.net_ok)
        ok = probe_network()
        if ok != self.net_ok:
            log.info('网络状态: %s', '已连接' if ok else '离线（握手将每 %d 分钟重试）' % self.cfg.net_retry_minutes)
        elif not ok:
            log.info('仍无网络，%d 分钟后再次握手', self.cfg.net_retry_minutes)
        self.net_ok = ok
        self._next_net_check = now + (60 if ok else self.cfg.net_retry_minutes * 60)
        return ok
    def run_collection(self, sources=None, collector_override=None):
        """采集一轮（限速见 collectors）。返回统计 dict。"""
        if not self._work_lock.acquire(blocking=False):
            raise Busy('已有采集/推送任务在进行')
        try:
            self.cfg.reload()
            stats = collect_all(self.db, self.cfg, sources=sources, collector_override=collector_override)
            self.last_stats = stats
            self.last_collect_at = datetime.now()
            self.apply_archive_policy()
            return stats
        finally:
            self._work_lock.release()
    def apply_archive_policy(self):
        try:
            days = self.cfg.archive_days
            n = self.db.archive_old(days)
            slimmed = self.db.archive_digests(days)
            for date, (body, stale) in slimmed.items():
                slim_digest_files(self.data_dir, date, body, stale)
            if n or slimmed:
                log.info('归档瘦身: %d 条目、%d 天简讯（保留标题+链接）', n, len(slimmed))
        except Exception:
            log.warning('归档策略执行失败', exc_info=True)
    def _maybe_enrich(self, sections):
        """文章API 可用时给每类前 N 条生成一句话摘要（失败不影响简讯）。"""
        if not self.cfg.article_api_enabled:
            return sections
        try:
            processor = ArticleProcessor.from_config(self.cfg.article_api)
            n = 0
            for sec in sections.values():
                picked = sec.get('items', [])[:self.cfg.article_api_limit]
                n += enrich_items(processor, picked, db=self.db)
            if n:
                log.info('文章API 更新 %d 条一句话摘要', n)
        except Exception:
            log.warning('文章API 处理跳过（不影响简讯）', exc_info=True)
        return sections
    def current_window(self):
        """(start, end)：起点=上次成功推送时刻，无则回退 24h。"""
        end = datetime.now()
        start = self.db.last_successful_push_time()
        if start:
            try:
                start_dt = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                start_dt = end - timedelta(hours=24)
        else:
            start_dt = end - timedelta(hours=24)
        return (start_dt, end)
    def build_sections(self, window_start=None, window_end=None):
        if window_start is None:
            window_start, window_end = self.current_window()
        elif window_end is None:
            window_end = datetime.now()
        items = self.db.window_items(window_start.strftime('%Y-%m-%d %H:%M:%S'), window_end.strftime('%Y-%m-%d %H:%M:%S'))
        return build_digest_sections(items, self.cfg)
    def preview_messages(self, kind='preview'):
        ws, we = self.current_window()
        sections = self.build_sections(ws, we)
        stale = summarize_stats(self.last_stats) if self.last_stats else None
        return build_messages(sections, we, self.cfg.channel_type, kind=kind, stale_line=stale, style=self.cfg.digest_style)
    def _make_channel(self):
        return create_channel(self.cfg, self.data_dir)
    def do_push(self, kind='scheduled', scheduled_for=None, collector_override=None):
        """采集→组稿→推送→落库 一体。返回 (ok, err, entry_count)。"""
        if not self._work_lock.acquire(blocking=False):
            raise Busy('已有采集/推送任务在进行')
        try:
            self.cfg.reload()
            window_start, _ = self.current_window()
            try:
                stats = collect_all(self.db, self.cfg, collector_override=collector_override)
                self.last_stats = stats
                self.last_collect_at = datetime.now()
            except Exception:
                log.error('推送前采集异常（继续用库内现有条目推送）', exc_info=True)
                stats = self.last_stats
            now = datetime.now()
            sections = self.build_sections(window_start, now)
            sections = self._maybe_enrich(sections)
            stale = summarize_stats(stats) if stats else None
            entry_count = sum((len(sec.get('items', [])) for sec in sections.values()))
            entries = entries_json(sections)
            time_str, date_str = now.strftime('%H:%M'), now.strftime('%Y-%m-%d')
            ws_str = window_start.strftime('%Y-%m-%d %H:%M:%S')
            we_str = now.strftime('%Y-%m-%d %H:%M:%S')
            def _archive(status, push_id=None):
                did = self.db.save_digest(date_str, time_str, kind, status, entry_count, entries, stale or '', self.cfg.channel_type, push_id)
                try:
                    title, body = build_messages(sections, now, 'mock', kind=kind, stale_line=stale or '', style=self.cfg.digest_style)[0]
                    write_md(self.data_dir, date_str, time_str, title, body)
                except Exception:
                    log.warning('简讯快照文件写入失败', exc_info=True)
                return did
            try:
                channel = self._make_channel()
            except PushError as e:
                _archive('local')
                self.db.record_push(kind, 'failed', self.cfg.channel_type, ws_str, we_str, entry_count, str(e), scheduled_for=scheduled_for)
                log.info('通道未配置，本窗口简讯已存档未发送: %s', e)
                return (False, str(e), entry_count)
            messages = build_messages(sections, now, channel.name, kind=kind, stale_line=stale, style=self.cfg.digest_style)
            ok, err = channel.send_all(messages)
            if ok:
                push_id = self.db.record_push(kind, 'success', channel.name, ws_str, we_str, entry_count, scheduled_for=scheduled_for)
                _archive('sent', push_id)
                items = self.db.window_items(ws_str, we_str)
                self.db.mark_pushed([it['id'] for it in items], push_id)
                self._push_fail_streak = 0
                log.info('推送成功: %d 条（%s），简讯已存档', entry_count, channel.name)
                return (True, '', entry_count)
            else:
                self.db.record_push(kind, 'failed', channel.name, ws_str, we_str, entry_count, err, scheduled_for=scheduled_for)
                self._push_fail_streak += 1
                log.warning('推送失败: %s', err)
                return (False, err, entry_count)
        finally:
            self._work_lock.release()
    def send_test_push(self):
        try:
            channel = self._make_channel()
        except PushError as e:
            return (False, str(e))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ok, err = channel.send('【测试】NewsHub 测试简讯', f"通道 {channel.name} 配置成功。\n测试时间: {now}\n收到本条说明手机推送链路正常，正式简讯将按 config 的推送时刻发送。")
        self.db.record_push('test', 'success' if ok else 'failed', channel.name, '', '', 0, err)
        return (ok, err)
    def check_and_push_due(self, collector_override=None):
        """心跳回调：到点就推。返回是否执行了推送。"""
        self.cfg.reload()
        if self._push_fail_streak >= self.cfg.push_retry_limit:
            return False
        if not self.cfg.channel_ready():
            return False
        last_ok = self.db.last_successful_push_time()
        now = datetime.now()
        try:
            anchor = last_ok and datetime.strptime(last_ok, '%Y-%m-%d %H:%M:%S') or now - timedelta(hours=24)
        except ValueError:
            anchor = now - timedelta(hours=24)
        due = []
        for day_offset in (2, 1, 0):
            day = (now - timedelta(days=day_offset)).date()
            for slot in self.cfg.today_push_datetimes(day):
                if anchor < slot <= now:
                    due.append(slot)
        if not due:
            return False
        if not self.cfg.catchup_enabled and (now - max(due)).total_seconds() > 1800:
            return False
        earliest = min(due)
        kind = 'scheduled' if len(due) == 1 and (now - max(due)).total_seconds() < 300 else 'catchup'
        log.info('到期推送 %d 个时刻（%s ~ %s），kind=%s', len(due), due[0].strftime('%m-%d %H:%M'), due[-1].strftime('%H:%M'), kind)
        try:
            ok, err, _ = self.do_push(kind, earliest.strftime('%Y-%m-%d %H:%M'), collector_override)
        except Busy:
            return False
        return ok
    def should_background_collect(self):
        if not self.last_collect_at:
            return True
        return (datetime.now() - self.last_collect_at).total_seconds() >= self.cfg.bg_collect_hours * 3600
