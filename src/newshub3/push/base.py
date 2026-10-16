"""push.base —— 推送通道抽象基类。"""
class PushError(Exception):
    """通道不可用（凭证缺失/配置错误）。"""
class BaseChannel:
    """子类实现 send(title, body) -> (ok, err)。name 用于日志与落库。"""
    name = 'base'
    def send(self, title, body):
        raise NotImplementedError
    def send_all(self, messages):
        """顺序发送多片消息；任一片失败即整体失败（返回首个错误）。"""
        errs = []
        for title, body in messages:
            ok, err = self.send(title, body)
            if not ok:
                errs.append(f'{title}: {err}')