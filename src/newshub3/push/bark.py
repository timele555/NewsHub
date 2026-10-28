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
        self.origin = f'{u.scheme}://{u.netloc}'
        path = u.path.strip('/')
        self.device_key = path.split('/')[0] if path else ''
        self.timeout = timeout
    def send(self, title, body):
        if not self.device_key:
            return (False, 'Bark URL 中未解析到 device_key')
        else:
            try:
                r = requests.post(self.origin + '/push', json={'device_key': self.device_key, 'title': str(title)[:60], 'body': body}, timeout=self.timeout)
                data = r.json()
            except ValueError:
                return (False, '响应非 JSON')
            except requests.RequestException as e:
                return (False, str(e)[:120])
            if data.get('code') == 200:
                return (True, '')
            return (False, f"code={data.get('code')} {str(data.get('message', ''))[:100]}")