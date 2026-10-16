"""logutil —— 日志：控制台 + 滚动文件，UTF-8。"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
def setup_logging(data_dir, verbose=False):
    os.makedirs(data_dir, exist_ok=True)
    log_path = os.path.join(data_dir, 'logs', 'newshub3.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S')
    fh = RotatingFileHandler(log_path, maxBytes=2097152, backupCount=5, encoding='utf-8')
    fh.setFormatter(fmt)
    root.addHandler(fh)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return log_path