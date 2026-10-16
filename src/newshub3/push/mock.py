"""push.mock —— 模拟通道：不发网，写本地文件，供凭证缺失/离线测试用。"""
import logging
import os
import threading
from .base import BaseChannel
log = logging.getLogger('newshub3.push.mock')
class MockChannel(BaseChannel):
    name = 'mock'
    def __init__(self, out_dir='data'):
        self.out = os.path.join(out_dir, 'mock_push.txt')
        self._lock = threading.Lock()
        os.makedirs(out_dir, exist_ok=True)
    def send(self, title, body):
        with self._lock:
            with open(self.out, 'a', encoding='utf-8') as f:
                pass