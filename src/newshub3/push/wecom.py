"""push.wecom —— 企业微信群机器人 Webhook（默认通道）。\n\n接口：POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx\n     {\"msgtype\": \"markdown\", \"markdown\": {\"content\": \"...\"}}，content ≤ 4096 字节。\n"""
import logging
import requests
from .base import BaseChannel
log = logging.getLogger('newshub3.push.wecom')
class WecomChannel(BaseChannel):
    name = 'wecom'
    def __init__(self, webhook, timeout=15):
        self.webhook = webhook.strip()
        self.timeout = timeout
    def send(self, title, body):
        content = f'### {title}\n{body}'
        if len(content.encode('utf-8')) > 4096:
            content = content.encode('utf-8')[:4000].decode('utf-8', 'ignore') + '…'
        try:
            r = requests.post(self.webhook, json={'msgtype': 'markdown', 'markdown': {'content': content}}, timeout=self.timeout)
            data = r.json()
        except ValueError:
            return (False, '响应非 JSON')
        except requests.RequestException as e:
            return (False, str(e)[:120])
        if data.get('errcode') == 0:
            return (True, '')