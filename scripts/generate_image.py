# -*- coding: utf-8 -*-
"""AiDash — D 部分：生成 1072×1448 Kindle 仪表盘图片（每日一图）

用法：
    python generate_image.py                 # 从 GitHub raw 读取数据（默认）
    python generate_image.py --local         # 读取脚本同目录下的 data.json / data.md / feeds.json
    python generate_image.py --out xxx.png   # 指定输出文件

依赖：pip install -r requirements.txt（本文件只用 Pillow）

数据来源：
    - data.json  待办/倒计时/笔记/购物/布局/设置（手机 App 保存）
    - data.md    AI 笔记（data.json 没有笔记时解析兜底）
    - feeds.json 资讯热榜（GitHub Actions 抓取）
    - Open-Meteo 天气（免费，无需 Key）

布局：按 data.json.layout.order 顺序竖排，heights 作为相对高度权重，
自动缩放铺满整张 1072×1448 画布，任何高度组合都不会留大片空白。
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

try:
    import config_local as CFG
except Exception:
    CFG = None

# ---------------- 画布与常量 ----------------
W = 1072          # Kindle Paperwhite 6 宽度
H = 1448          # Kindle Paperwhite 6 高度
MARGIN = 18       # 外白边
GAP = 10          # 面板间距
HEADER_H = 150    # 顶部时钟面板固定高度
PANEL_TITLE_H = 46  # 面板标题区高度

WEEK = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

DEFAULT_QUOTES = [
    "读书不觉已春深，一寸光阴一寸金。",
    "不积跬步，无以至千里；不积小流，无以成江海。",
    "知之者不如好之者，好之者不如乐之者。",
    "路漫漫其修远兮，吾将上下而求索。",
    "纸上得来终觉浅，绝知此事要躬行。",
    "凡事预则立，不预则废。",
]

KNOWN_MODULES = {"weather", "feeds", "countdown", "todo", "notes", "quote"}


# ---------------- 配置与字体 ----------------
def get_cfg(key, default):
    # 环境变量优先（GitHub Actions 里用环境变量注入配置/密钥）
    if os.environ.get(key):
        return os.environ.get(key)
    if CFG is not None and hasattr(CFG, key) and getattr(CFG, key):
        return getattr(CFG, key)
    return default


FONT_CANDIDATES = [
    # Windows：微软雅黑 / 黑体 / 宋体
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    # macOS：苹方 / 冬青黑体
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    # Linux：思源黑体 / 文泉驿
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

MONO_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]

_font_path = None
_mono_path = None
_cache = {}


def font(size):
    """中文字体（按需缓存）"""
    global _font_path
    if _font_path is None:
        _font_path = get_cfg("FONT_PATH", "") or next(
            (p for p in FONT_CANDIDATES if os.path.exists(p)), None
        )
        if not _font_path:
            sys.exit("找不到中文字体！请把字体路径填到 config_local.py 的 FONT_PATH")
    key = ("f", size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(_font_path, size)
    return _cache[key]


def font_mono(size):
    """等宽数字字体（时钟用；找不到就退回中文字体）"""
    global _mono_path
    if _mono_path is None:
        _mono_path = next((p for p in MONO_CANDIDATES if os.path.exists(p)), None)
    key = ("m", size)
    if key not in _cache:
        if _mono_path:
            _cache[key] = ImageFont.truetype(_mono_path, size)
        else:
            _cache[key] = font(size)
    return _cache[key]


# ---------------- 文本工具 ----------------
def tw(draw, s, f):
    """文字宽度"""
    return draw.textlength(s, font=f)


def truncate(draw, s, f, max_w):
    """超宽截断并加省略号"""
    s = str(s)
    if tw(draw, s, f) <= max_w:
        return s
    t = s
    while t and tw(draw, t + "…", f) > max_w:
        t = t[:-1]
    return t + "…"


def wrap_lines(draw, s, f, max_w):
    """按像素宽度换行"""
    lines = []
    cur = ""
    for ch in str(s):
        if tw(draw, cur + ch, f) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


# ---------------- 面板通用 ----------------
def panel_title(draw, box, title):
    """面板标题：左侧黑竖条 + 标题文字 + 底部细线（沿用网页版风格）"""
    x, y, w, h = box
    draw.rectangle([x + 18, y + 12, x + 23, y + 34], fill="black")
    draw.text((x + 32, y + 9), title, font=font(26), fill="black")
    draw.line([x + 18, y + 46, x + w - 18, y + 46], fill=(224, 224, 224), width=2)


def placeholder(draw, box, msg="暂无数据"):
    """数据缺失时的占位提示"""
    x, y, w, h = box
    draw.text((x + 22, y + 58), msg, font=font(23), fill=(140, 140, 140))


# ---------------- 各模块绘制 ----------------
def draw_header(draw, box, now):
    """顶部：大时钟 + 日期 + 问候语（仿网页版时钟面板）"""
    x, y, w, h = box
    draw.rounded_rectangle([x, y, x + w, y + h], radius=22, outline="black", width=3)

    t = now.strftime("%H:%M")
    tf = font_mono(78)
    draw.text((x + (w - tw(draw, t, tf)) / 2, y + 6), t, font=tf, fill="black")

    date_s = "%d年%d月%d日 %s" % (now.year, now.month, now.day, WEEK[now.weekday()])
    df = font(27)
    draw.text((x + (w - tw(draw, date_s, df)) / 2, y + 90), date_s, font=df, fill="black")

    hh = now.hour
    greet = (
        "夜深了，早点休息" if hh < 6 else
        "早上好，元气满满" if hh < 12 else
        "下午好，继续加油" if hh < 18 else
        "晚上好，放松一下"
    )
    gf = font(20)
    draw.text((x + (w - tw(draw, greet, gf)) / 2, y + 121), greet, font=gf, fill=(90, 90, 90))

    label = "AiDash 每日仪表盘"
    lf = font(16)
    draw.text((x + w - 20 - tw(draw, label, lf), y + 10), label, font=lf, fill=(120, 120, 120))


def draw_weather(draw, box, weather):
    """天气：当前天气大字 + 湿度风速 + 未来 3~5 天预报"""
    x, y, w, h = box
    panel_title(draw, box, "天气预报")
    if not weather:
        placeholder(draw, box, "天气加载失败（离线模式无网络）")
        return
    cy = y + PANEL_TITLE_H + 6
    cf = font(34)
    draw.text((x + 20, cy), truncate(draw, weather.get("cur", ""), cf, w - 40), font=cf, fill="black")
    cy += 46
    sf = font(22)
    draw.text((x + 20, cy), truncate(draw, weather.get("sub", ""), sf, w - 40), font=sf, fill=(70, 70, 70))
    cy += 31
    ff = font(21)
    for line in weather.get("fc", []):
        if cy + 30 > y + h - 4:
            break
        draw.text((x + 20, cy), truncate(draw, line, ff, w - 40), font=ff, fill="black")
        cy += 29


def draw_feeds(draw, box, cats):
    """资讯热榜：B站/知乎/微博/IT之家/少数派/UP主动态"""
    x, y, w, h = box
    panel_title(draw, box, "资讯热榜")
    if not cats:
        placeholder(draw, box, "暂无资讯（GitHub Actions 抓取后自动显示）")
        return
    cy = y + PANEL_TITLE_H + 4
    cat_h = 30
    item_h = 28
    for label, items in cats:
        if cy + cat_h + item_h > y + h - 6:
            break
        draw.rectangle([x + 18, cy + 5, x + 22, cy + 23], fill="black")
        draw.text((x + 30, cy), label, font=font(23), fill="black")
        cy += cat_h
        for it in items:
            if cy + item_h > y + h - 6:
                break
            draw.text(
                (x + 36, cy),
                truncate(draw, it, font(20), w - 56),
                font=font(20),
                fill=(40, 40, 40),
            )
            cy += item_h


def draw_countdown(draw, box, data):
    """倒计时：剩余天数"""
    x, y, w, h = box
    panel_title(draw, box, "重要倒计时")
    counts = data.get("countdowns") or []
    if not counts:
        placeholder(draw, box, "暂无倒计时")
        return
    row_h = 40
    content_h = h - PANEL_TITLE_H - 8
    rows = max(1, min(len(counts), int((content_h - 4) / row_h)))
    cy = y + PANEL_TITLE_H + 4
    for c in counts[:rows]:
        name = str(c.get("name", ""))
        date = str(c.get("date", ""))
        d = days_until(date)
        if d is None:
            txt = "日期格式错误"
        elif d > 0:
            txt = "还有 %d 天" % d
        elif d == 0:
            txt = "就是今天！"
        else:
            txt = "已过 %d 天" % (-d)
        line = "%s：%s" % (name, txt)
        draw.text((x + 20, cy), truncate(draw, line, font(25), w - 40), font=font(25), fill="black")
        cy += row_h


def draw_todo(draw, box, data):
    """安排/待办：复选框 + 优先级徽标 + 截止日期 + 底部进度条
    排序：未完成在前（高→中→低，再按截止日期），已完成置后。
    """
    x, y, w, h = box
    panel_title(draw, box, "安排 / 待办")
    todos = data.get("todos") or []
    if not todos:
        placeholder(draw, box, "暂无待办，让手机里的 AI 秘书帮你安排")
        return

    pri_idx = {"高": 0, "中": 1, "低": 2}

    def sort_key(t):
        return (
            1 if t.get("done") else 0,
            pri_idx.get(t.get("priority"), 1),
            t.get("dueDate") or "9999-99-99",
        )

    todos = sorted(todos, key=sort_key)
    row_h = 48
    content_h = h - PANEL_TITLE_H - 30  # 底部预留进度条
    rows = max(1, min(len(todos), int((content_h - 4) / row_h)))
    cy = y + PANEL_TITLE_H + 4
    for t in todos[:rows]:
        done = bool(t.get("done"))
        text_s = str(t.get("text", ""))
        pri = str(t.get("priority") or "中")
        if pri not in pri_idx:
            pri = "中"

        # 复选框
        draw.rectangle([x + 20, cy + 5, x + 37, cy + 22], outline="black", width=2)
        if done:
            draw.line([x + 24, cy + 13, x + 28, cy + 18], fill="black", width=2)
            draw.line([x + 28, cy + 18, x + 34, cy + 9], fill="black", width=2)

        # 优先级徽标
        bx = x + 46
        lf = font(18)
        bw = int(tw(draw, pri, lf)) + 12
        if pri == "高":
            draw.rounded_rectangle([bx, cy + 2, bx + bw, cy + 25], radius=6, fill="black")
            draw.text((bx + 6, cy + 4), pri, font=lf, fill="white")
        else:
            draw.rounded_rectangle([bx, cy + 2, bx + bw, cy + 25], radius=6, outline="black", width=1)
            draw.text((bx + 6, cy + 4), pri, font=lf, fill=(110, 110, 110) if pri == "低" else "black")

        # 任务文字
        tx = bx + bw + 8
        tf = font(24)
        color = (120, 120, 120) if done else "black"
        tline = truncate(draw, text_s, tf, w - 20 - (tx - x))
        draw.text((tx, cy + 1), tline, font=tf, fill=color)
        if done:
            wl = tw(draw, tline, tf)
            draw.line([tx, cy + 15, tx + wl, cy + 15], fill=(120, 120, 120), width=2)

        # 截止日期
        due = t.get("dueDate") or ""
        if due:
            draw.text((tx, cy + 25), "截止 " + due, font=font(16), fill=(130, 130, 130))
        cy += row_h

    # 底部进度条
    done_n = sum(1 for t in todos if t.get("done"))
    pct = int(round(done_n * 100 / len(todos)))
    py = y + h - 26
    draw.text((x + 20, py), "进度", font=font(19), fill=(90, 90, 90))
    px = x + 20 + int(tw(draw, "进度", font(19))) + 8
    block = 12
    gapb = 4
    filled = round(pct / 10)
    for i in range(10):
        bx2 = px + i * (block + gapb)
        if i < filled:
            draw.rectangle([bx2, py + 3, bx2 + block, py + 3 + block], fill="black")
        else:
            draw.rectangle([bx2, py + 3, bx2 + block, py + 3 + block], outline="black", width=1)
    txt2 = "%d%%（%d/%d）" % (pct, done_n, len(todos))
    draw.text((px + 10 * (block + gapb) + 8, py), txt2, font=font(19), fill=(60, 60, 60))


def draw_notes(draw, box, notes):
    """AI 笔记摘要：文字 + #标签"""
    x, y, w, h = box
    panel_title(draw, box, "AI 笔记")
    if not notes:
        placeholder(draw, box, "暂无笔记")
        return
    row_h = 46
    content_h = h - PANEL_TITLE_H - 8
    rows = max(1, min(len(notes), int((content_h - 4) / row_h)))
    cy = y + PANEL_TITLE_H + 4
    nf = font(23)
    tf = font(17)
    for n in notes[:rows]:
        if isinstance(n, dict):
            text_s = str(n.get("text", ""))
            tags = n.get("tags") or []
        else:
            text_s = str(n)
            tags = []
        line = truncate(draw, text_s, nf, w - 52)
        draw.text((x + 22, cy), "· " + line, font=nf, fill="black")
        if tags:
            tag_s = "#" + " #".join(str(t) for t in tags[:3])
            draw.text((x + 34, cy + 24), truncate(draw, tag_s, tf, w - 56), font=tf, fill=(130, 130, 130))
        cy += row_h


def draw_quote(draw, box, quote):
    """每日一言：居中显示"""
    x, y, w, h = box
    panel_title(draw, box, "每日一言")
    if not quote:
        quote = "博观而约取，厚积而薄发。"
    qf = font(28)
    lines = wrap_lines(draw, quote, qf, w - 60)
    line_h = 36
    total = len(lines) * line_h
    cy = y + (h - total) / 2 + 8
    for ln in lines:
        draw.text((x + (w - tw(draw, ln, qf)) / 2, cy), ln, font=qf, fill="black")
        cy += line_h


# ---------------- 数据获取 ----------------
def fetch_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AiDash/1.0",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "ignore")


def fetch_json(url):
    return json.loads(fetch_text(url))


def load_remote(name, local):
    """读取 GitHub raw 文件或本地文件（local 模式用于测试）"""
    if local:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    base = get_cfg("RAW_BASE", "")
    return fetch_text(base.rstrip("/") + "/" + name)


def load_json(name, local):
    try:
        return json.loads(load_remote(name, local))
    except Exception:
        return {}


def load_text(name, local):
    try:
        return load_remote(name, local)
    except Exception:
        return ""


def wmo(code):
    """Open-Meteo 天气代码 → 中文描述"""
    table = {
        0: "晴", 1: "多云", 2: "阴", 3: "阴",
        45: "雾", 48: "雾",
        51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
        56: "冻雨", 57: "冻雨",
        61: "雨", 63: "雨", 65: "雨",
        66: "冻雨", 67: "冻雨",
        71: "雪", 73: "雪", 75: "雪", 77: "雪",
        80: "阵雨", 81: "阵雨", 82: "阵雨",
        85: "阵雪", 86: "阵雪",
    }
    if code in table:
        return table[code]
    if code is not None and code >= 95:
        return "雷雨"
    return "未知"


def fetch_weather(lat, lon, city):
    """从 Open-Meteo 拉取天气，组装成绘制用的字典"""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=%s&longitude=%s"
        "&current_weather=true"
        "&hourly=relative_humidity_2m"
        "&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset"
        "&timezone=auto&forecast_days=5"
    ) % (urllib.parse.quote(str(lat)), urllib.parse.quote(str(lon)))
    try:
        d = fetch_json(url)
    except Exception:
        return None
    try:
        cw = d.get("current_weather") or {}
        temp = round(cw.get("temperature", 0))
        desc = wmo(cw.get("weathercode"))

        # 当前小时湿度
        hum = "--"
        try:
            times = (d.get("hourly") or {}).get("time") or []
            harr = (d.get("hourly") or {}).get("relative_humidity_2m") or []
            prefix = datetime.now().strftime("%Y-%m-%dT%H:")
            for i, t in enumerate(times):
                if str(t).startswith(prefix):
                    hum = "%d%%" % harr[i]
                    break
        except Exception:
            pass

        wind = round(cw.get("windspeed", 0))
        sub = "湿度 %s ｜ 风速 %d km/h" % (hum, wind)

        fc = []
        dl = d.get("daily") or {}
        days = dl.get("time") or []
        names = ["今天", "明天", "后天"]
        wk = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        n = min(5, len(days))
        for i in range(n):
            label = names[i] if i < 3 else wk[datetime.strptime(days[i], "%Y-%m-%d").weekday()]
            rain_arr = dl.get("precipitation_probability_max") or []
            rain = rain_arr[i] if i < len(rain_arr) and rain_arr[i] is not None else None
            rain_txt = (" 降水%d%%" % round(rain)) if rain is not None else ""
            line = "%s：%s %d~%d°C%s" % (
                label,
                wmo(dl["weathercode"][i]),
                round(dl["temperature_2m_min"][i]),
                round(dl["temperature_2m_max"][i]),
                rain_txt,
            )
            fc.append(line)

        sr = (dl.get("sunrise") or [""])[0]
        ss = (dl.get("sunset") or [""])[0]
        if sr and ss:
            fc.append("日出 %s ｜ 日落 %s" % (sr[11:16], ss[11:16]))

        return {"cur": "%s %s %d°C" % (city, desc, temp), "sub": sub, "fc": fc}
    except Exception:
        return None


def normalize_feeds(raw):
    """把 feeds.json 归一化成 [(分类名, [标题…]), …]，最多取前 4 个分类"""
    cats = []
    order = [
        ("bili", "B站热搜"),
        ("zhihu", "知乎热榜"),
        ("weibo", "微博热搜"),
        ("ithome", "IT之家"),
        ("sspai", "少数派"),
    ]
    for key, label in order:
        items = raw.get(key)
        if isinstance(items, list):
            t = [str(i) for i in items if str(i).strip()][:4]
            if t:
                cats.append((label, t))
    ups = raw.get("ups")
    if isinstance(ups, list):
        for u in ups:
            if not isinstance(u, dict):
                continue
            name = str(u.get("name") or "")
            titles = [str(t) for t in (u.get("titles") or []) if str(t).strip()][:2]
            if name and titles:
                cats.append((name, titles))
    return cats[:4]


def parse_notes_from_md(md_text):
    """从 data.md 的“## 笔记”小节解析笔记（data.json 没有笔记时兜底）"""
    notes = []
    m = re.search(r"##\s*笔记(.*?)(?:\n##\s|\Z)", md_text, re.S)
    if not m:
        return notes
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("- "):
            t = line[2:].strip()
            if t and t != "_暂无_":
                tags = re.findall(r"#([^\s#]+)", t)
                clean = re.sub(r"#([^\s#]+)", "", t).strip()
                notes.append({"text": clean or t, "tags": tags})
            if len(notes) >= 6:
                break
    return notes


def days_until(date_str):
    try:
        target = datetime.strptime(str(date_str), "%Y-%m-%d").date()
        return (target - datetime.now().date()).days
    except Exception:
        return None


def get_quotes():
    q = get_cfg("QUOTES", [])
    if isinstance(q, list) and q:
        return q
    return DEFAULT_QUOTES


# ---------------- 组装画布 ----------------
def build(now, data, feeds, weather, notes, quote):
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    layout = data.get("layout") or {}
    order = [m for m in (layout.get("order") or []) if m in KNOWN_MODULES]
    if not order:
        order = ["weather", "feeds", "countdown", "todo", "notes", "quote"]
    heights = layout.get("heights") or {}

    # 顶部时钟
    draw_header(draw, (MARGIN, MARGIN, W - 2 * MARGIN, HEADER_H), now)

    # 其余面板：按 heights 作为相对权重，自动缩放铺满剩余空间
    y = MARGIN + HEADER_H + 12
    remaining = H - y - 16 - GAP * (len(order) - 1)
    total_w = sum(max(40, int(heights.get(m, 160))) for m in order)
    scale = remaining / float(total_w) if total_w else 1.0

    for m in order:
        ph = max(40, int(round(int(heights.get(m, 160)) * scale)))
        box = (MARGIN, y, W - 2 * MARGIN, ph)
        if m == "weather":
            draw_weather(draw, box, weather)
        elif m == "feeds":
            draw_feeds(draw, box, feeds)
        elif m == "countdown":
            draw_countdown(draw, box, data)
        elif m == "todo":
            draw_todo(draw, box, data)
        elif m == "notes":
            draw_notes(draw, box, notes)
        elif m == "quote":
            draw_quote(draw, box, quote)
        y += ph + GAP

    return img


def main():
    ap = argparse.ArgumentParser(description="生成 AiDash 每日 Kindle 仪表盘图片")
    ap.add_argument("--local", action="store_true", help="读取脚本同目录的本地数据文件（测试用）")
    ap.add_argument("--out", default=None, help="输出文件路径")
    args = ap.parse_args()

    now = datetime.now()
    data = load_json("data.json", args.local)
    md_text = load_text("data.md", args.local)
    feeds_raw = load_json("feeds.json", args.local)

    settings = data.get("settings") or {}
    city = str(settings.get("city") or get_cfg("CITY", "温州"))
    lat = str(settings.get("lat") or get_cfg("LAT", "27.99"))
    lon = str(settings.get("lon") or get_cfg("LON", "120.70"))

    # 天气：远程模式实时拉取；本地模式支持 weather.json 兜底（测试用）
    weather = None
    if args.local:
        weather = load_json("weather.json", True) or None
    if not weather:
        try:
            weather = fetch_weather(lat, lon, city)
        except Exception:
            weather = None

    notes = data.get("notes") or []
    if not notes:
        notes = parse_notes_from_md(md_text)

    feeds = normalize_feeds(feeds_raw)
    quotes = get_quotes()
    quote = quotes[now.toordinal() % len(quotes)]

    img = build(now, data, feeds, weather, notes, quote)
    out = args.out or get_cfg("OUT_IMAGE", "dashboard_1072x1448.png")
    img.save(out)
    print("已生成 %s（%dx%d）" % (out, W, H))


if __name__ == "__main__":
    main()
