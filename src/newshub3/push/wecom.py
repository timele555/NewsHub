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
            pass
        try:
            data = r.json()
        except ValueError:
            pass
        except requests.RequestException as e:
            pass
        if data.get('errcode') == 0:
            return (True, '')