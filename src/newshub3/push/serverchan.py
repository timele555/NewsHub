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
            data = r.json()
        except ValueError:
            pass
        if data.get('code') == 0:
            return (True, '')