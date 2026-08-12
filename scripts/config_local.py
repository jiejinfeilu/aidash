# -*- coding: utf-8 -*-
"""AiDash 本地配置（D/E 部分使用）—— 请根据自己情况修改。

注意：这个文件不要上传到 GitHub（真实密钥请放这里或系统环境变量）。
"""

# GitHub raw 数据地址（改成【你的 GitHub 用户名】）
RAW_BASE = "https://raw.githubusercontent.com/jiejinfeilu/aidash/main"

# 城市与坐标（data.json 里的 settings 会优先于这里的值）
CITY = "温州"
LAT = "27.99"
LON = "120.70"

# 中文字体路径：留空自动查找（Windows 微软雅黑 / macOS 苹方 / Linux 思源黑体）
FONT_PATH = ""

# 输出图片路径
OUT_IMAGE = "dashboard_1072x1448.png"

# 每日一言列表：留空使用内置默认
QUOTES = []

# SMTP 发信配置（E 部分 send_to_kindle.py 使用）
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
SMTP_USER = ""              # 你的发件邮箱，如 xxx@qq.com
SMTP_AUTH_CODE = ""         # 邮箱授权码（不是登录密码）
SMTP_FROM = ""              # 发件人显示名，如 "AiDash"
KINDLE_EMAIL = ""           # Kindle 收件邮箱（国际账户的 xxx@kindle.com）
