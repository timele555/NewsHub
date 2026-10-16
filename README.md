# NewsHub —— 资讯自动采集与简报推送

16 个内置信息源、8 类采集器（RSS / HTML / 公开 API），定时把分类简讯推送到 QQ 邮箱（亦支持企业微信 / Server酱 / Bark），带本地仪表盘、标题墙、日历、简讯存档（30 天滚动归档）与内置 Agent 工作台（自然语言订阅 / 抓取 / 推送）。

## 功能速览

- **采集**：RSS（量子位/少数派/爱范儿/IEEE Spectrum 等）、智东西/智源/HF Daily Papers/42号车库 页面解析、虎嗅/华尔街见闻接口、财新头条提示
- **推送**：SMTP 邮箱（465 SSL / 587 STARTTLS 自适应）、企业微信机器人、Server酱、Bark；错过补发
- **仪表盘**：内置 HTTP 服务（默认 127.0.0.1:8367），标题墙/列表视图、日历回看、来源健康、拖拽文件直发邮箱
- **Agent**：`订阅 <URL> 的 xx 内容，抓完推给我` / `把库里关于 xx 的内容报一版` 等中文指令
- **自检**：`--doctor` 全量自检（配置/数据库/端口/网络/来源抽检/SMTP 握手），报告落盘 `data/logs/selfcheck.txt`

## 目录结构

```
src/main.py            入口（argparse 调度）
src/newshub3/          业务包（collectors 采集 / push 通道 / dashboard 仪表盘 / core 核心 / …）
installer/installer.py 安装向导（tkinter，/S 静默 /U 卸载）
config/                config.template.json 配置模板
docs/原版说明.txt        功能与命令行说明
```

## 快速开始

```bash
pip install -r requirements.txt
```

复制 `config/config.template.json` 为 `config.json`（程序每分钟自动重读，无需重启），按注释填写 SMTP 授权码等。

```bash
python src/main.py --doctor-quick     # 离线自检
python src/main.py                    # 常驻运行
python src/main.py --collect          # 手动采集一轮
python src/main.py --preview          # 打印简讯预览
```

## License

MIT
