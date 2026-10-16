"""push.bark —— Bark（iOS）。\n\n用官方 POST /push JSON 接口（GET 拼 URL 会因中文编码超长 414）：\n  POST {origin}/push  {\"device_key\": \"...\", \"title\": \"...\", \"body\": \"...\"}\nconfig 里 Bark_推送URL 形如 https://api.day.app/你的Key，自动解析出 device_key。\n"""
import logging
from urllib.parse import urlparse
import requests
from .base import BaseChannel
log = logging.getLogger('newshub3.push.bark')
class BarkChannel(BaseChannel):
    name = 'bark'
    def __init__(self, bark_url, timeout=15):
        u = urlparse(bark_url.strip().rstrip('/'))
        self.timeout = timeout
    def send(self, title, body):
        if not self.device_key:
            return (False, 'Bark URL 中未解析到 device_key')
        else:
            try:
                data = r.json()
            except ValueError:
                pass
            except requests.RequestException as e:
                pass
            if data.get('code') == 200:
                return (True, '')