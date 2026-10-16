"""scheduler.py —— 心跳线程：cron 语义的定时器。\n\n每 cfg.heartbeat_sec 秒醒来一次：\n1. 重读 config（改推送时刻 1 分钟内生效，无需重启）；\n2. 检查到期/错过的计划推送（含休眠补发，见 core.check_and_push_due）；\n3. 距上次采集超过设定小时数则做一轮背景采集。\n"""
import logging
import threading
log = logging.getLogger('newshub3.scheduler')
class Heartbeat(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True, name='heartbeat')
        self.app = app
        self._stop = threading.Event()
    def stop(self):
        self._stop.set()
    def run(self):
        while not self._stop.is_set():
            waited = 0.0
            interval = self.app.cfg.heartbeat_sec
            if self._stop.is_set():
                return
            else:
                try:
                    pass
                except Exception:
                    log.exception('心跳 tick 异常（不影响下一轮）')
    def tick(self):
        app = self.app
        err = app.cfg.reload()
        if err:
            log.warning('%s', err)
        if not app.ensure_network():
            return
        else:
            app.check_and_push_due()
            if app.should_background_collect():
                try:
                    stats = app.run_collection()
                except Exception as e:
                    log.warning('背景采集跳过: %s', e)