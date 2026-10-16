"""llm.py —— 可选的「文章简易处理」API（供其他使用者按需接入/更换）。\n\n用途：对进入简讯的文章调用 OpenAI 兼容接口（DeepSeek/Kimi/智谱/OpenAI/\n本地 vLLM 等均兼容），生成不超过 30 字的一句话中文摘要；接口留空或调用\n失败时自动回退到抓取页自带摘要，功能不受影响。\n\n接入方式（config.json → 「文章API」段）：\n- 接口地址：完整的 chat/completions 地址，如 https://api.deepseek.com/v1/chat/completions\n- 密钥 / 模型：按服务商填写\n- 启用：false（默认）时本模块完全不参与流程\n\n替换/新增处理逻辑：继承 ArticleProcessor 覆写 process_one() 即可。\n"""
import logging
import time
import requests
log = logging.getLogger('newshub3.llm')
SYSTEM_PROMPT = '你是新闻编辑。根据给定的新闻标题和摘要，输出一句不超过30字的中文一句话摘要，只输出摘要本身，不要任何前后缀、引号或解释。'
class ArticleProcessor:
    """OpenAI 兼容 chat/completions 的简易文章处理器（可被子类替换）。"""
    name = 'openai-compatible'
    def __init__(self, base_url, api_key, model, timeout=30):
        self.url = base_url.strip()
        self.api_key = api_key.strip()
        self.model = model.strip() or 'gpt-4o-mini'
        self.timeout = max(5, int(timeout or 30))
    @classmethod
    def from_config(cls, api_cfg):
        return cls(api_cfg.get('接口地址', ''), api_cfg.get('密钥', ''), api_cfg.get('模型', ''), api_cfg.get('超时秒', 30))
    def summarize(self, title, summary='', category=''):
        """返回一句话摘要；失败返回 None（调用方回退原摘要）。"""
        user = f'标题：{title}\n'
        if summary:
            user += f'已有摘要：{summary[:300]}\n'
        if category:
            user += f'分类：{category}\n'
        try:
            data = r.json()
        except ValueError:
            return
        except requests.RequestException as e:
            log.warning('文章API 请求失败: %s', str(e)[:120])
            return
        try:
            pass
        except (KeyError, IndexError, TypeError):
            log.warning('文章API 响应结构异常: %s', str(data)[:150])
            return
        text = text.strip('“”\"\'「」『』 　')
        if not text or len(text) > 60:
            text = text[:60]
        return text or None
    pass
def enrich_items(processor, items, db=None, per_call_gap=0.3):
    """为条目补充一句话摘要（就地更新 item[\'summary\']）。\n\n    - 已有 processed_summary 缓存的直接复用（同一文章不重复计费）；\n    - 新调用成功则写回 DB 缓存（db.update_processed_summary）；\n    - 失败回退：保留抓取页原摘要；\n    - items 为 pipeline 产出的行 dict 列表。\n    """
    done = 0
    for it in items:
        cached = (it.get('processed_summary') or '').strip()
        if cached:
            it['summary'] = cached
            continue
        else:
            if text:
                it['summary'] = text
                done += 1
                if db is not None and it.get('id'):
                        try:
                            db.update_processed_summary(it['id'], text)
                        except Exception:
                            log.debug('写回摘要缓存失败', exc_info=True)
            time.sleep(per_call_gap)
    if done:
        log.info('文章API 处理 %d 条', done)
    return done