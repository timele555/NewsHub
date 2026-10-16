"""push —— 可替换推送通道接口。\n\n统一契约：channel.send(title, body) -> (ok: bool, err: str)\n新增通道只需实现 BaseChannel 子类并在 __init__.py 工厂注册。\n"""
from .base import BaseChannel, PushError
from .wecom import WecomChannel
from .serverchan import ServerChanChannel
from .bark import BarkChannel
from .smtp_channel import SmtpChannel
from .mock import MockChannel
def create_channel(cfg, data_dir=None):
    """按 config「推送.通道」构造对应通道对象；凭证缺失抛 PushError（由调用方转为失败记录）。\n\n    data_dir 仅 mock 通道使用（模拟输出文件位置）。\n    """
    t = cfg.channel_type
    timeout = cfg.send_timeout
    if t == 'wecom':
        if not cfg.webhook:
            raise PushError('企业微信 Webhook 未填写（config.json → 推送.企业微信_Webhook）')
        else:
            return WecomChannel(cfg.webhook, timeout)
    else:
        if t == 'serverchan':
            if not cfg.serverchan_key:
                raise PushError('Server酱 SendKey 未填写')
            else:
                return ServerChanChannel(cfg.serverchan_key, timeout)
        else:
            if t == 'bark':
                if not cfg.bark_url:
                    raise PushError('Bark 推送 URL 未填写')
                else:
                    return BarkChannel(cfg.bark_url, timeout)
            else:
                if t == 'smtp':
                    s = cfg.smtp
                    if not all([s['服务器'], s['账号'], s['授权码'], s['收件人']]):
                        raise PushError('SMTP 配置不完整（服务器/账号/授权码/收件人）')
                    else:
                        return SmtpChannel(s, timeout)
                else:
                    if t == 'mock':
                        pass
                    else:
                        raise PushError(f'未知推送通道: {t}（可选 wecom/serverchan/bark/smtp/mock）')
__all__ = ['BaseChannel', 'PushError', 'create_channel']