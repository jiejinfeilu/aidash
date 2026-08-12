# AiDash — F 部分：定时任务设置

有两类定时任务：

| 任务 | 频率 | 作用 |
|---|---|---|
| 抓热榜（feeds.yml） | 每 30 分钟 | 更新仓库根目录的 `feeds.json`（B站/知乎/微博/IT之家/少数派/UP主） |
| 每日推送（daily_push.yml） | 每天 07:30（北京时间） | 生成仪表盘图 → 打包 EPUB → 发到 Kindle 邮箱 |

## 方案一：GitHub Actions（推荐，电脑不用开机）

免费额度：每月 2000 分钟。抓热榜约 48 次/天 + 每日推送 1 次，合计约 500 分钟/月，远低于限额。

### 1. 上传工作流文件

把 `aidash/.github/workflows/` 里的两个文件（`feeds.yml`、`daily_push.yml`）上传到 GitHub 仓库的同一路径。
上传方法：仓库 Code → Add file → **Create new file**，文件名逐级输入 `.github/workflows/feeds.yml`，粘贴内容，Commit；`daily_push.yml` 同理。
同时把 `scripts/fetch-feeds.js` 上传到 `scripts/` 目录。

### 2. 配置 6 个 Secrets（每日推送用）

仓库 Settings → **Secrets and variables → Actions** → New repository secret，逐个添加：

| Secret 名 | 值 |
|---|---|
| SMTP_HOST | `smtp.qq.com`（或其他邮箱服务器） |
| SMTP_PORT | `465` |
| SMTP_USER | 你的发件邮箱，如 `xxx@qq.com` |
| SMTP_AUTH_CODE | 邮箱授权码（QQ 邮箱设置 → 账户 → 开启 SMTP 生成） |
| SMTP_FROM | `AiDash`（发件人显示名，可随意） |
| KINDLE_EMAIL | 国际账户的 `xxx@kindle.com` |

> 这些 Secrets 只有 GitHub Actions 能看到，仓库文件里不出现任何真实密钥。

### 3. 手动触发一次测试

仓库 Actions 标签页 → 左侧 “Daily Kindle Push” → 右侧 **Run workflow** → 绿色 Run。
第一次最好先到手机/电脑上确认：邮箱收到 EPUB 附件、Kindle 收到书。

### 4. 修改推送时间

GitHub Actions 的 cron 是 **UTC 时间**，北京时间要减 8 小时：

| 想要北京时间 | cron 填写 |
|---|---|
| 07:30（默认） | `30 23 * * *` |
| 08:00 | `0 0 * * *` |
| 22:00 | `14 14 * * *` |

改 `daily_push.yml` 里的 `- cron: ...` 那行，提交后生效。

## 方案二：Windows 任务计划程序（本地电脑跑）

适合不想用 GitHub Actions、或想让脚本在本地跑的情况。
需要先在 `scripts/config_local.py` 里填好 SMTP 和 Kindle 邮箱，然后：

### 方法 A：命令行创建（推荐，复制即用）

```powershell
schtasks /create /tn "AiDash每日推送" /tr "\"C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\pythonw.exe\" \"C:\path\to\aidash\scripts\send_to_kindle.py\"" /sc daily /st 07:30
```

- `pythonw.exe` 无控制台黑窗口；找不到就用 `python.exe`
- 路径里有空格必须用 `\"...\"` 包裹
- 创建后可用 `schtasks /run /tn "AiDash每日推送"` 手动测试一次

### 方法 B：图形界面

1. 按 `Win` 搜索“任务计划程序”打开
2. 右侧“创建基本任务”→ 名称 `AiDash每日推送`
3. 触发器选“每天”，时间 07:30
4. 操作选“启动程序”：程序填 `pythonw.exe` 完整路径，参数填 `send_to_kindle.py` 的完整路径
5. 完成；右键任务“运行”可测试

## 方案三：macOS / Linux（cron）

编辑 `crontab -e`，加一行（每天 07:30）：

```bash
30 7 * * * cd /path/to/aidash/scripts && /usr/bin/python3 send_to_kindle.py >> /tmp/aidash_kindle.log 2>&1
```

查日志：`cat /tmp/aidash_kindle.log`

## 常见问题

- **Actions 里发信失败**：检查 6 个 Secrets 是否填对；QQ 邮箱确认已开启 SMTP 并生成的是**授权码**；Kindle 邮箱必须是国际账户 `@kindle.com`。
- **Kindle 收不到**：到 amazon.com → 管理我的内容和设备 → 个人文档设置，把发件邮箱加入“已批准的个人文档电子邮件列表”；推送后等 1~5 分钟，Kindle 连上 Wi-Fi 会自动下载。
- **Actions 没按点跑**：cron 用的是 UTC；GitHub 偶尔延迟几分钟属正常。
- **免费额度**：feeds 每 30 分钟 + 每日推送，月用量约 500 分钟，免费档 2000 分钟够用。
- **不想用 Actions 抓热榜**：可以在本地定期运行 `node scripts/fetch-feeds.js` 后手动提交，或用方案二/三定时跑 `generate_image.py`。
