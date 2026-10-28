"""push.serverchan —— Server酱（sct.ftqq.com），通道③之一。"""
import logging
import requests
from .base import BaseChannel
log = logging.getLogger('newshub3.push.serverchan')
class ServerChanChannel(BaseChannel):
    name = 'serverchan'
    def __init__(self, sendkey, timeout=15):
        self.key = sendkey.strip()
        self.timeout = timeout
    def send(self, title, body):
        try:
            r = requests.post('https://sctapi.ftqq.com/' + self.key + '.send', data={'title': str(title)[:32], 'desp': body}, timeout=self.timeout)
            data = r.json()
        except ValueError:
            return (False, '响应非 JSON')
        except requests.RequestException as e:
            return (False, str(e)[:120])
        if data.get('code') == 0:
            return (True, '')
        return (False, f"code={data.get('code')} {str(data.get('message', ''))[:100]}")