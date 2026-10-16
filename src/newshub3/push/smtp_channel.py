"""push.smtp —— 邮箱推送（通道④），SSL 465 或 STARTTLS 587 自适应。"""
import logging
import re
import smtplib
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from .base import BaseChannel
log = logging.getLogger('newshub3.push.smtp')
class SmtpChannel(BaseChannel):
    name = 'smtp'
    def __init__(self, smtp_cfg, timeout=15):
        self.host = smtp_cfg['服务器']
        self.port = int(smtp_cfg.get('端口', 465))
        self.user = smtp_cfg['账号']
        self.pwd = smtp_cfg['授权码']
        self.to = smtp_cfg['收件人']
        self.timeout = timeout
    @staticmethod
    def _add_standard_headers(msg, user):
        """补 Date / Message-ID（正规 MUA 均携带，缺失易被收件方垃圾评分）。"""
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=user.split('@')[-1] if '@' in user else 'local')
    def send(self, title, body):
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(title, 'utf-8')
        msg['From'] = formataddr(('NewsHub', self.user))
        msg['To'] = self.to
        self._add_standard_headers(msg, self.user)
        return self._deliver(msg)
    def send_files(self, files, note=''):
        """首页「拖拽直发」：把一批文件作为附件发到绑定邮箱。

        files: [(文件名, bytes), ...]。文件名只用于附件头（清洗换行/引号防注入）。
        """
        msg = MIMEMultipart()
        msg['Subject'] = Header(f'【快发】NewsHub 文件直送（{len(files)} 个附件）', 'utf-8')
        msg['From'] = formataddr(('NewsHub', self.user))
        msg['To'] = self.to
        self._add_standard_headers(msg, self.user)
        msg.attach(MIMEText(note or '来自 NewsHub 首页拖拽直发的文件。', 'plain', 'utf-8'))
        for fname, blob in files:
            part = MIMEApplication(blob)
            safe = re.sub("[\\r\\n\"']", '_', str(fname))[:120] or 'file'
            part.add_header('Content-Disposition', 'attachment', filename=safe)
            msg.attach(part)
        return self._deliver(msg)
    def _deliver(self, msg):
        """登录并发送一封已构建好的邮件 → (ok, err)。"""
        try:
            if self.port == 465:
                srv = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout)
            else:
                srv = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                srv.starttls()
            try:
                srv.login(self.user, self.pwd)
                srv.sendmail(self.user, [x.strip() for x in self.to.split(',') if x.strip()], msg.as_string())
            finally:
                srv.quit()
            return (True, '')
        except (smtplib.SMTPException, OSError) as e:
            return (False, f'{type(e).__name__}: {str(e)[:150]}')
def verify_smtp(server, port, user, auth, rcpt, timeout=15, send_test=True):
    """首次绑定邮箱的握手：登录验证（可选发一封测试邮件）→ (ok, err)。

    465 走 SSL、587 走 STARTTLS、其余端口按 SSL 尝试。
    """
    try:
        port = int(port or 465)
    except (TypeError, ValueError):
        port = 465
    msg = MIMEText(f"你的邮箱推送绑定成功。此后简报将按设定的推送时刻发送到本邮箱。\n服务器: {server}:{port} · 账号: {user}", 'plain', 'utf-8')
    msg['Subject'] = Header('【握手成功】NewsHub 邮箱绑定测试', 'utf-8')
    msg['From'] = formataddr(('NewsHub', user))
    msg['To'] = rcpt
    SmtpChannel._add_standard_headers(msg, user)
    try:
        if port == 587:
            srv = smtplib.SMTP(server, port, timeout=timeout)
            srv.starttls()
        else:
            srv = smtplib.SMTP_SSL(server, port, timeout=timeout)
        try:
            code, resp = srv.login(user, auth)
            if code != 235:
                return (False, f'登录被拒绝({code}): {str(resp)[:100]}（请检查授权码）')
            if send_test:
                srv.sendmail(user, [x.strip() for x in rcpt.split(',') if x.strip()], msg.as_string())
            return (True, '')
        finally:
            try:
                srv.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError as e:
        return (False, f'认证失败: {str(e)[:120]}（授权码错误或未开启 SMTP 服务）')
    except smtplib.SMTPServerDisconnected as e:
        return (False, f'连接被服务器关闭：多为授权码连续错误被临时限制或网络不稳定，请核对授权码后稍后重试（{type(e).__name__}: {str(e)[:80]}）')
    except (smtplib.SMTPException, OSError) as e:
        return (False, f'{type(e).__name__}: {str(e)[:150]}')
