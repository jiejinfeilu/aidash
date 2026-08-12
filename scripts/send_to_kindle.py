# -*- coding: utf-8 -*-
"""AiDash — E 部分：每日仪表盘 → EPUB → 推送到 Kindle

流程：
    1. 调用 generate_image.py 生成 1072×1448 仪表盘图
    2. 用 Python 内置 zipfile 打包一个标准 EPUB（封面 = 仪表盘图）
    3. 通过 SMTP 发送到 Kindle 邮箱（国际账户的 xxx@kindle.com）
    4. （可选 --mobi）本机装了 Calibre 时另转一份 .mobi 供 USB 拷贝

重要说明：
    - 2022 年 8 月起，亚马逊“发送至 Kindle”邮件不再接受 .mobi，
      改为接受 .epub（会自动转换并保留封面），所以这里直接发 EPUB。
    - @kindle.cn 邮箱已停用，必须使用国际账户的 @kindle.com 邮箱，
      并把发件邮箱加入 Kindle 账户的“已批准个人文档邮件列表”。

用法：
    python send_to_kindle.py                  # 完整流程：生成图片 → 打包 → 发送
    python send_to_kindle.py --image x.png    # 跳过生成，使用已有图片
    python send_to_kindle.py --no-send        # 只生成 EPUB 不发送（先预览）
    python send_to_kindle.py --mobi           # 额外用 Calibre 转一份 .mobi
    python send_to_kindle.py --out-dir tmp/   # 指定输出目录

依赖：pip install -r requirements.txt（本文件只需 Pillow；EPUB 用内置库）
"""
import argparse
import datetime
import os
import shutil
import smtplib
import ssl
import subprocess
import sys
import zipfile
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

try:
    import config_local as CFG
except Exception:
    CFG = None


def get_cfg(key, default):
    # 环境变量优先（GitHub Actions 里用环境变量注入 SMTP 配置/密钥）
    if os.environ.get(key):
        return os.environ.get(key)
    if CFG is not None and hasattr(CFG, key) and getattr(CFG, key):
        return getattr(CFG, key)
    return default


HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------- 第 1 步：生成仪表盘图片 ----------------
def ensure_image(args, out_dir):
    """生成或复用仪表盘图片"""
    if args.image:
        p = os.path.abspath(args.image)
        if not os.path.exists(p):
            sys.exit("找不到图片：%s" % p)
        print("使用已有图片：%s" % p)
        return p

    stamp = datetime.date.today().strftime("%Y%m%d")
    img = os.path.join(out_dir, "dashboard_%s.png" % stamp)
    gen = os.path.join(HERE, "generate_image.py")
    if not os.path.exists(gen):
        sys.exit("找不到 generate_image.py（应与本文件在同一目录）")
    print("步骤 1/3：生成仪表盘图片…")
    try:
        subprocess.run([sys.executable, gen, "--out", img], check=True)
    except subprocess.CalledProcessError:
        sys.exit("生成图片失败，请先单独运行 generate_image.py 排查")
    return img


# ---------------- 第 2 步：打包 EPUB ----------------
def build_epub(image_path, out_path, title, uid):
    """用 zipfile 生成最小合法 EPUB，封面 = 仪表盘图片

    EPUB 本质是一个 zip，包含：
      mimetype（第一个文件、不压缩）、META-INF/container.xml、
      OEBPS/content.opf（书目信息 + 封面元数据）、toc.ncx、
      nav.xhtml、封面页、内容页和图片本身。
    """
    with open(image_path, "rb") as f:
        cover_bytes = f.read()

    date_s = datetime.date.today().strftime("%Y-%m-%d")
    modified = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    title_esc = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    uid_esc = uid.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    container_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )

    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="zh-CN">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">%s</dc:identifier>\n'
        '    <dc:title>%s</dc:title>\n'
        '    <dc:language>zh-CN</dc:language>\n'
        '    <dc:creator>AiDash</dc:creator>\n'
        '    <meta property="dcterms:modified">%s</meta>\n'
        '    <meta name="cover" content="cover-image"/>\n'
        '  </metadata>\n'
        '  <manifest>\n'
        '    <item id="cover-image" href="cover.png" media-type="image/png"/>\n'
        '    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="dash" href="dash.xhtml" media-type="application/xhtml+xml"/>\n'
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
        '  </manifest>\n'
        '  <spine toc="ncx">\n'
        '    <itemref idref="cover"/>\n'
        '    <itemref idref="dash"/>\n'
        '  </spine>\n'
        '</package>\n'
    ) % (uid_esc, title_esc, modified)

    nav_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">\n'
        '<head><title>目录</title><meta charset="utf-8"/></head>\n'
        '<body>\n'
        '  <nav epub:type="toc"><h1>目录</h1>\n'
        '    <ol>\n'
        '      <li><a href="cover.xhtml">封面（仪表盘）</a></li>\n'
        '      <li><a href="dash.xhtml">说明</a></li>\n'
        '    </ol>\n'
        '  </nav>\n'
        '</body>\n'
        '</html>\n'
    )

    toc_ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-CN">\n'
        '  <head>\n'
        '    <meta name="dtb:uid" content="%s"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n'
        '  </head>\n'
        '  <docTitle><text>AiDash 每日仪表盘</text></docTitle>\n'
        '  <navMap>\n'
        '    <navPoint id="np-1" playOrder="1"><navLabel><text>封面</text></navLabel><content src="cover.xhtml"/></navPoint>\n'
        '    <navPoint id="np-2" playOrder="2"><navLabel><text>说明</text></navLabel><content src="dash.xhtml"/></navPoint>\n'
        '  </navMap>\n'
        '</ncx>\n'
    ) % uid_esc

    cover_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
        '<head><title>封面</title><meta charset="utf-8"/></head>\n'
        '<body style="margin:0;text-align:center;background:#ffffff">\n'
        '  <img src="cover.png" alt="AiDash 每日仪表盘" style="max-width:100%%;height:auto"/>\n'
        '</body>\n'
        '</html>\n'
    )

    dash_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
        '<head><title>说明</title><meta charset="utf-8"/></head>\n'
        '<body style="padding:24px;line-height:1.8;color:#111">\n'
        '  <h1>AiDash 每日仪表盘</h1>\n'
        '  <p>%s</p>\n'
        '  <p>在 Kindle 上打开这本书，然后休眠（锁屏），'
        '屏幕就会显示封面上的全屏仪表盘。</p>\n'
        '  <p>设置路径：Kindle 设置 → 设备选项 → 高级选项 → 显示封面（开启）。</p>\n'
        '</body>\n'
        '</html>\n'
    ) % date_s

    with zipfile.ZipFile(out_path, "w") as z:
        # mimetype 必须是第一个文件，且不压缩（EPUB 规范要求）
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", toc_ncx.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/cover.xhtml", cover_xhtml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/dash.xhtml", dash_xhtml.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/cover.png", cover_bytes, compress_type=zipfile.ZIP_DEFLATED)

    return out_path


# ---------------- 第 3 步：SMTP 发送 ----------------
def send_email(host, port, user, auth_code, sender_name, to, subject, epub_path):
    """通过 SMTP 发送 EPUB 附件到 Kindle 邮箱"""
    if not (host and user and auth_code and to):
        sys.exit(
            "SMTP 配置不完整：请先在 config_local.py 填写\n"
            "  SMTP_HOST / SMTP_USER / SMTP_AUTH_CODE / KINDLE_EMAIL"
        )
    if not os.path.exists(epub_path):
        sys.exit("找不到 EPUB：%s" % epub_path)

    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(sender_name or "AiDash", "utf-8")), user))
    msg["To"] = to
    msg["Subject"] = str(Header(subject, "utf-8"))

    with open(epub_path, "rb") as f:
        part = MIMEApplication(f.read(), _subtype="epub+zip")
    part.add_header("Content-Disposition", "attachment", filename=os.path.basename(epub_path))
    msg.attach(part)
    msg.attach(MIMEText(
        "附件是今日 AiDash 仪表盘（EPUB）。\n"
        "在 Kindle 上打开这本书，休眠时锁屏就会显示封面仪表盘。\n\n"
        "—— AiDash",
        "plain", "utf-8",
    ))

    port = int(port or 465)
    print("步骤 3/3：正在通过 SMTP 发送到 %s …" % to)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())
        server.login(user, auth_code)
        server.sendmail(user, [to], msg.as_string())
        server.quit()
    except smtplib.SMTPAuthenticationError:
        sys.exit("SMTP 登录失败：请检查授权码是否正确（授权码 ≠ 邮箱登录密码）")
    except Exception as e:
        sys.exit("SMTP 发送失败：%s" % e)


# ---------------- 可选：Calibre 转 MOBI（仅供 USB 本地用） ----------------
def maybe_convert_mobi(epub_path, out_dir):
    exe = shutil.which("ebook-convert")
    if not exe:
        for cand in (
            r"C:/Program Files/Calibre2/ebook-convert.exe",
            r"C:/Program Files (x86)/Calibre2/ebook-convert.exe",
        ):
            if os.path.exists(cand):
                exe = cand
                break
    if not exe:
        print("提示：未找到 Calibre 的 ebook-convert，跳过 MOBI 转换。")
        print("（本方案用不到 MOBI——邮件推送发 EPUB 即可；MOBI 仅供 USB 拷贝时使用）")
        return
    mobi = os.path.splitext(epub_path)[0] + ".mobi"
    print("正在用 Calibre 转换 MOBI（仅供 USB 使用）…")
    try:
        subprocess.run([exe, epub_path, mobi], check=True)
        print("已生成：%s" % mobi)
    except subprocess.CalledProcessError:
        print("MOBI 转换失败（不影响 EPUB 推送）。")


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="生成每日仪表盘 EPUB 并推送到 Kindle")
    ap.add_argument("--image", default=None, help="使用已有图片，跳过生成步骤")
    ap.add_argument("--no-send", action="store_true", help="只生成 EPUB，不发送邮件")
    ap.add_argument("--mobi", action="store_true", help="额外用 Calibre 转一份 MOBI（可选）")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "output"), help="输出目录")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    today = datetime.date.today()
    stamp = today.strftime("%Y%m%d")
    date_s = today.strftime("%Y-%m-%d")

    img = ensure_image(args, args.out_dir)

    epub_path = os.path.join(args.out_dir, "aidash_%s.epub" % stamp)
    print("步骤 2/3：打包 EPUB…")
    build_epub(img, epub_path, "AiDash 每日仪表盘 %s" % date_s, "aidash-%s" % stamp)
    print("已生成：%s" % epub_path)

    if args.mobi:
        maybe_convert_mobi(epub_path, args.out_dir)

    if args.no_send:
        print("已跳过发送（--no-send）。")
        return

    send_email(
        host=get_cfg("SMTP_HOST", "smtp.qq.com"),
        port=get_cfg("SMTP_PORT", 465),
        user=get_cfg("SMTP_USER", ""),
        auth_code=get_cfg("SMTP_AUTH_CODE", ""),
        sender_name=get_cfg("SMTP_FROM", "AiDash"),
        to=get_cfg("KINDLE_EMAIL", ""),
        subject="AiDash 每日仪表盘 %s" % date_s,
        epub_path=epub_path,
    )
    print("发送成功！")
    kindle = get_cfg("KINDLE_EMAIL", "")
    print("提示：请确认 %s 已在 Kindle 账户的“已批准个人文档邮件列表”中，否则会被拒收。" % kindle)


if __name__ == "__main__":
    main()
