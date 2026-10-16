"""db.py —— SQLite 持久层：条目 / 推送记录 / 来源健康 / 元数据。

去重策略：URL＋标题 归一化后拼接取 sha1 作 dedup_key，建 UNIQUE 索引，
重复插入直接被数据库拒绝（并发安全）。
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime
def now_str():
    """本地时间 ISO 字符串（秒级），用于统一比较。"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def normalize_url(url):
    """URL 归一化：去首尾空格与结尾斜杠，去常见追踪参数，压小写协议头之后的路径大小写不敏感部分。"""
    u = (url or '').strip()
    u = re.sub('[?&](utm_[^=&]+|spm|from|scene|chksm|share_token|ref)=[^&]*', '', u)
    return u.rstrip('/')
def normalize_title(title):
    """标题归一化：去所有空白与全半角差异。"""
    t = (title or '').strip()
    t = re.sub('\\s+', '', t)
    table = {ord(a): ord(b) for a, b in zip('０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ：｜', '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz:|')}
    return t.translate(table)
def make_dedup_key(url, title):
    raw = normalize_url(url) + '|' + normalize_title(title)
    return hashlib.sha1(raw.encode('utf-8', 'ignore')).hexdigest()
class Database:
    """SQLite 薄封装。check_same_thread=False + 自管互斥锁（采集/推送/服务跨线程共享）。"""

    def __init__(self, db_path):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript('\n            CREATE TABLE IF NOT EXISTS articles (\n              id            INTEGER PRIMARY KEY AUTOINCREMENT,\n              category      TEXT NOT NULL,\n              source        TEXT NOT NULL,\n              title         TEXT NOT NULL,\n              summary       TEXT DEFAULT \'\',\n              url           TEXT NOT NULL,\n              dedup_key     TEXT NOT NULL UNIQUE,\n              published_at  TEXT,\n              collected_at  TEXT NOT NULL,\n              pushed_push_id INTEGER,\n              is_notice     INTEGER DEFAULT 0\n            );\n            CREATE INDEX IF NOT EXISTS idx_articles_collected ON articles(collected_at);\n            CREATE INDEX IF NOT EXISTS idx_articles_pushed    ON articles(pushed_push_id);\n            CREATE INDEX IF NOT EXISTS idx_articles_category  ON articles(category);\n\n            CREATE TABLE IF NOT EXISTS pushes (\n              push_id      INTEGER PRIMARY KEY AUTOINCREMENT,\n              pushed_at    TEXT NOT NULL,\n              scheduled_for TEXT,\n              kind         TEXT NOT NULL,          -- scheduled / catchup / test / manual\n              status       TEXT NOT NULL,          -- success / failed\n              channel      TEXT,\n              window_start TEXT,\n              window_end   TEXT,\n              entry_count  INTEGER DEFAULT 0,\n              detail       TEXT DEFAULT \'\'\n            );\n\n            CREATE TABLE IF NOT EXISTS source_health (\n              source     TEXT PRIMARY KEY,\n              last_ok    TEXT,\n              last_fail  TEXT,\n              fail_count INTEGER DEFAULT 0,\n              last_error TEXT DEFAULT \'\',\n              last_count INTEGER DEFAULT 0\n            );\n\n            CREATE TABLE IF NOT EXISTS digests (\n              digest_id   INTEGER PRIMARY KEY AUTOINCREMENT,\n              push_id     INTEGER,\n              date        TEXT NOT NULL,           -- YYYY-MM-DD（推送时刻所属日期）\n              time        TEXT NOT NULL,           -- HH:MM\n              kind        TEXT,                    -- scheduled / catchup / manual\n              status      TEXT NOT NULL,           -- sent / failed / local(未配置通道仅存档)\n              channel     TEXT,\n              entry_count INTEGER DEFAULT 0,\n              stale_line  TEXT DEFAULT \'\',\n              sections    TEXT NOT NULL,           -- JSON 数组：分类/标题/摘要/链接（链接永久保留）\n              archived    INTEGER DEFAULT 0        -- 超过归档期后已瘦身（仅标题+链接）\n            );\n            CREATE INDEX IF NOT EXISTS idx_digests_date ON digests(date);\n\n            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);\n            ')
            try:
                self._conn.execute('ALTER TABLE articles ADD COLUMN is_archived INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE articles ADD COLUMN processed_summary TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    def insert_article(self, category, source, title, url, summary='', published_at=None, collected_at=None, is_notice=False):
        """插入条目，重复返回 False。字段统一在此收口清洗。"""
        title = re.sub('<[^>]+>', ' ', title or '').strip()
        summary = re.sub('<[^>]+>', ' ', summary or '').strip()
        if not title or not (url or '').strip():
            return False
        url = normalize_url(url)
        key = make_dedup_key(url, title)
        with self._lock:
            try:
                self._conn.execute('INSERT INTO articles(category,source,title,summary,url,dedup_key,published_at,collected_at,pushed_push_id,is_notice) VALUES(?,?,?,?,?,?,?,?,NULL,?)', (category.strip() or '未分类', source.strip(), title, summary, url.strip(), key, published_at, collected_at or now_str(), 1 if is_notice else 0))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                self._conn.commit()
                return False

    def window_items(self, window_start, window_end):
        """窗口内未推送条目（含跨窗口漏网但未推送的，保证不重不漏）。"""
        with self._lock:
            rows = self._conn.execute('SELECT * FROM articles WHERE collected_at > ? AND collected_at <= ? AND pushed_push_id IS NULL ORDER BY COALESCE(published_at, collected_at) DESC', (window_start, window_end)).fetchall()
        return [dict(r) for r in rows]

    def mark_pushed(self, article_ids, push_id):
        if not article_ids:
            return
        with self._lock:
            self._conn.executemany('UPDATE articles SET pushed_push_id=? WHERE id=?', [(push_id, aid) for aid in article_ids])
            self._conn.commit()

    def update_processed_summary(self, article_id, text):
        """缓存文章API生成的一句话摘要。"""
        with self._lock:
            self._conn.execute('UPDATE articles SET processed_summary=? WHERE id=?', (text, article_id))
            self._conn.commit()

    def articles_for_dashboard(self, category=None, date_str=None, search=None, limit=500):
        """仪表盘查询：按分类/日期/关键词筛选。"""
        sql, args = ('SELECT * FROM articles WHERE 1=1', [])
        if category and category != '全部':
            sql += ' AND category=?'
            args.append(category)
        if date_str and date_str != '全部':
            sql += ' AND substr(COALESCE(published_at,collected_at),1,10)=?'
            args.append(date_str)
        if search:
            sql += ' AND (title LIKE ? OR summary LIKE ? OR source LIKE ?)'
            args += [f'%{search}%'] * 3
        sql += ' ORDER BY COALESCE(published_at, collected_at) DESC LIMIT ?'
        args.append(max(1, min(2000, int(limit))))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def dashboard_dates(self):
        """现有条目的日期列表（供筛选下拉框）。"""
        with self._lock:
            rows = self._conn.execute('SELECT DISTINCT substr(COALESCE(published_at,collected_at),1,10) AS d FROM articles ORDER BY d DESC LIMIT 60').fetchall()
        return [r['d'] for r in rows]

    def article_date_counts(self, limit=180):
        """每日条目数（供日历面板标注哪些天有内容）。"""
        with self._lock:
            rows = self._conn.execute('SELECT substr(COALESCE(published_at,collected_at),1,10) d, COUNT(*) c FROM articles GROUP BY d ORDER BY d DESC LIMIT ?', (limit,)).fetchall()
        return {r['d']: r['c'] for r in rows}

    def categories(self):
        with self._lock:
            rows = self._conn.execute('SELECT DISTINCT category FROM articles ORDER BY category').fetchall()
        return [r['category'] for r in rows]

    def count(self):
        with self._lock:
            row = self._conn.execute('SELECT COUNT(*) c FROM articles').fetchone()
        return row['c'] if row else 0

    def record_push(self, kind, status, channel='', window_start='', window_end='', entry_count=0, detail='', scheduled_for=None, pushed_at=None):
        """写一条推送记录，返回 push_id。pushed_at 供测试伪造历史推送；生产路径默认当前时间。"""
        with self._lock:
            cur = self._conn.execute('INSERT INTO pushes(pushed_at,scheduled_for,kind,status,channel,window_start,window_end,entry_count,detail) VALUES(?,?,?,?,?,?,?,?,?)', (pushed_at or now_str(), scheduled_for, kind, status, channel, window_start, window_end, entry_count, detail))
            self._conn.commit()
            return cur.lastrowid

    def last_successful_push_time(self, default=None):
        """上次成功推送时刻（窗口起点）。没有记录时返回 default（首次运行只推最近窗口）。"""
        with self._lock:
            row = self._conn.execute("SELECT pushed_at FROM pushes WHERE status='success' ORDER BY pushed_at DESC LIMIT 1").fetchone()
        return row['pushed_at'] if row else default

    def recent_pushes(self, limit=20):
        with self._lock:
            rows = self._conn.execute('SELECT * FROM pushes ORDER BY pushed_at DESC, push_id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def save_digest(self, date, time_str, kind, status, entry_count, sections_json, stale_line='', channel='', push_id=None):
        """存档一份简讯（含全部条目标题+摘要+链接）。返回 digest_id。"""
        with self._lock:
            cur = self._conn.execute('INSERT INTO digests(date,time,kind,status,entry_count,sections,stale_line,channel,push_id) VALUES(?,?,?,?,?,?,?,?,?)', (date, time_str, kind, status, entry_count, sections_json, stale_line, channel, push_id))
            self._conn.commit()
            return cur.lastrowid

    def get_digests(self, date):
        """某日期的全部存档简讯（按时间倒序）。"""
        with self._lock:
            rows = self._conn.execute('SELECT * FROM digests WHERE date=? ORDER BY time DESC, digest_id DESC', (date,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d['entries'] = json.loads(d.pop('sections') or '[]')
            except ValueError:
                d['entries'] = []
            out.append(d)
        return out

    def digest_dates(self, limit=180):
        """有存档简讯的日期及份数（供日历面板），最近在前。"""
        with self._lock:
            rows = self._conn.execute('SELECT date, COUNT(*) c FROM digests GROUP BY date ORDER BY date DESC LIMIT ?', (limit,)).fetchall()
        return {r['date']: r['c'] for r in rows}

    def archive_old(self, days):
        """超过 N 天的条目瘦身：清空摘要、标记已归档，标题与链接永久保留。

        返回本次瘦身的条目数。归档数据仍在安装路径的 news.db 内。
        """
        with self._lock:
            cur = self._conn.execute("UPDATE articles SET summary='', is_archived=1 WHERE is_archived=0 AND COALESCE(published_at, collected_at) < date('now', ?)", (f'-{days} days',))
            self._conn.commit()
            return cur.rowcount

    def archive_digests(self, days):
        """超过 N 天的存档简讯瘦身：sections 内仅保留 标题+链接（去摘要）。

        返回 {date: [瘦身后的 entries JSON, stale_line]} 供调用方同步改写 .md 文件。
        """
        slimmed = {}
        with self._lock:
            rows = self._conn.execute("SELECT digest_id, date, stale_line, sections FROM digests WHERE archived=0 AND date < date('now', ?)", (f'-{days} days',)).fetchall()
            for r in rows:
                try:
                    entries = json.loads(r['sections'] or '[]')
                except ValueError:
                    entries = []
                slim = [{k: e.get(k, False if k == 'is_notice' else '') for k in ('category', 'title', 'url', 'is_notice')} for e in entries]
                body = json.dumps(slim, ensure_ascii=False)
                self._conn.execute('UPDATE digests SET sections=?, archived=1 WHERE digest_id=?', (body, r['digest_id']))
                slimmed[r['date']] = (body, r['stale_line'])
            self._conn.commit()
        return slimmed

    def update_source_health(self, source, ok, count=0, error=''):
        with self._lock:
            row = self._conn.execute('SELECT fail_count FROM source_health WHERE source=?', (source,)).fetchone()
            now = now_str()
            if ok:
                self._conn.execute("INSERT INTO source_health(source,last_ok,last_fail,fail_count,last_error,last_count) VALUES(?,?,NULL,0,'',?) ON CONFLICT(source) DO UPDATE SET last_ok=excluded.last_ok, fail_count=0, last_error='', last_count=excluded.last_count", (source, now, count))
            else:
                fc = ((row['fail_count'] if row else 0) or 0) + 1
                self._conn.execute("INSERT INTO source_health(source,last_ok,last_fail,fail_count,last_error,last_count) VALUES(?,NULL,?,?,?,0) ON CONFLICT(source) DO UPDATE SET last_fail=excluded.last_fail, fail_count=excluded.fail_count, last_error=excluded.last_error, last_count=excluded.last_count", (source, now, fc, str(error)[:300]))
            self._conn.commit()

    def source_health_all(self):
        with self._lock:
            rows = self._conn.execute('SELECT * FROM source_health ORDER BY source').fetchall()
        return [dict(r) for r in rows]

    def get_meta(self, key, default=None):
        with self._lock:
            row = self._conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_meta(self, key, value):
        with self._lock:
            self._conn.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()
