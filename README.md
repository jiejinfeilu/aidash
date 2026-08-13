# AiDash 个人生活驾驶舱

> 手机随手记 → AI 秘书安排 → GitHub 存储 → 每日仪表盘 → Kindle 锁屏封面

AiDash 是你的“个人生活秘书”：

- 手机上像 APP 一样的 PWA，随时用**文字或拍照**记录琐碎信息；
- AI（默认 DeepSeek）像秘书一样分析：提炼待办、判断优先级、推算截止日期、生成倒计时和笔记，并说明**为什么这样安排**；
- 你确认后写入 GitHub 仓库（`data.json` + `data.md`）；
- 每天早上自动生成一张 1072×1448 仪表盘图（天气/热榜/安排/倒计时/笔记/一言），打包成 EPUB 推送到 Kindle；
- Kindle 休眠时，锁屏就显示这张全屏仪表盘。

---

## 目录结构

```text
aidash/
├── README.md                  # 本文件（H 部分：使用手册）
├── docs/
│   ├── architecture.md        # A：架构说明 + 服务注册清单
│   ├── C-backend.md           # C：Vercel 部署步骤
│   ├── F-scheduling.md        # F：定时任务设置
│   └── G-kindle-setup.md      # G：Kindle 端操作
├── web/                       # B：手机 PWA（GitHub Pages）
│   ├── index.html
│   ├── config.js              # ← 部署后要改这里的地址
│   ├── manifest.webmanifest
│   ├── sw.js
│   └── icons/
├── api/                       # C：Vercel 后端
│   ├── process.js             # AI 秘书分析
│   ├── save.js                # 写回 GitHub
│   └── _lib/
├── vercel.json
├── .env.example               # 环境变量模板
├── scripts/                   # D/E：本地 Python 脚本
│   ├── generate_image.py      # 生成仪表盘图片
│   ├── send_to_kindle.py      # 打包 EPUB 并推送
│   ├── fetch-feeds.js         # 抓热榜（Actions 用）
│   ├── config_local.py        # 本地配置（SMTP/坐标/字体）
│   └── requirements.txt
└── .github/workflows/         # F：定时任务
    ├── feeds.yml              # 每 30 分钟抓热榜
    └── daily_push.yml         # 每天 07:30 推送 Kindle
```

`data.json`、`data.md`、`feeds.json` 是运行时文件，**不用手动创建**：
第一次在手机上保存时自动生成前两个，Actions 首次跑完生成第三个。

---

## 从零到一：完整设置清单

全程约 1 小时，按顺序做：

### 第 1 步：准备 7 个服务（详见 docs/architecture.md）

| 服务 | 要做什么 |
|---|---|
| GitHub | 新建仓库 `aidash`；开 Pages；建 fine-grained Token（Contents 读写）；开 Actions 写权限 |
| Vercel | 用 GitHub 登录（后面部署用） |
| DeepSeek | 注册、创建 API Key、充值 ¥10~50 |
| 邮箱（QQ 推荐） | 设置 → 账户 → 开启 SMTP，生成授权码 |
| Kindle | 确认是国际账户，记下 `@kindle.com` 邮箱（G 部分） |
| OpenAI（可选） | 想用 OpenAI 时才注册 |
| Open-Meteo | 不用注册，知道城市经纬度即可 |

### 第 2 步：上传全部文件到 GitHub

仓库 Code → Add file → **Upload files**，把本机 `aidash` 文件夹里的内容拖进去提交。
包含：`web/`、`api/`、`scripts/`、`docs/`、`.github/`、`vercel.json`、`.env.example`、`README.md`。

上传前改两处占位（都写着 `YOUR_GITHUB_USERNAME`）：

- `web/config.js` → `RAW_BASE` 改成 `https://raw.githubusercontent.com/你的用户名/aidash/main`
- `scripts/config_local.py` → `RAW_BASE` 同样改成你的用户名

> 安全提醒：如果你在 `scripts/config_local.py` 里填了**真实 SMTP 授权码**（本地方案），
> 这个文件就不要上传仓库；用 GitHub Actions 方案的话保持为空即可上传。

### 第 3 步：Vercel 部署后端（详见 docs/C-backend.md）

1. vercel.com → Add New → Project → Import `aidash`；
2. Framework Preset 选 **Other**，构建命令留空；
3. 添加 9 个环境变量（`AI_PROVIDER`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、
   `OPENAI_API_KEY`、`OPENAI_MODEL`、`GITHUB_TOKEN`、`GITHUB_REPO`、`GITHUB_BRANCH`、`APP_PIN`）；
4. Deploy，记下地址 `https://aidash-xxxxx.vercel.app`；
5. 用文档里的 curl 命令测一下 `/api/process` 和 `/api/save`。

### 第 4 步：手机安装 PWA 并连接

1. 手机浏览器打开 `https://jiejinfeilu.github.io/aidash/web/`；
2. iPhone：分享按钮 → **添加到主屏幕**（安卓：菜单 → 添加到主屏幕/安装应用）；
3. 打开 App → 设置 → 连接：
   - 后端地址：`https://aidash-xxxxx.vercel.app`
   - GitHub 数据地址：`https://raw.githubusercontent.com/你的用户名/aidash/main`
   - 口令：与 `APP_PIN` 相同
4. 保存连接，回“记录”页测试一次“AI 秘书处理”。

### 第 5 步：配置定时任务（详见 docs/F-scheduling.md）

1. 仓库 Settings → Secrets and variables → Actions，添加 6 个 Secret：
   `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_AUTH_CODE`、`SMTP_FROM`、`KINDLE_EMAIL`；
2. Actions 页面 → **Daily Kindle Push** → Run workflow，手动触发一次；
3. 等 1~10 分钟，确认邮箱收到 EPUB、Kindle 收到书。

### 第 6 步：Kindle 端设置（详见 docs/G-kindle-setup.md）

- 确认国际账户、`@kindle.com` 邮箱、发件邮箱白名单；
- 设置 → 设备选项 → 高级选项 → **显示封面** 打开；
- 推送到达后，点开“AiDash 每日仪表盘”一次，按电源键休眠 → 锁屏显示仪表盘。

### 第 7 步：验收清单

- [ ] 手机上输入“周六前把房租转给房东”→ AI 给出高优先级待办且截止日期是周六
- [ ] 点“保存到云端”→ GitHub 仓库出现 `data.json` 和 `data.md`
- [ ] 仓库 Actions 里 “Fetch Hotlists” 显示成功，`feeds.json` 有内容
- [ ] 手动 Run “Daily Kindle Push” 成功，Kindle 收到书
- [ ] Kindle 锁屏显示全屏仪表盘（含天气、热榜、你的待办）

---

## 每天怎么用

**早上（自动化）**

07:30 前后 GitHub Actions 自动生成今天的仪表盘并发到 Kindle。
你只需：打开 Kindle 上今天那本书 → 锁屏 → 屏保就是仪表盘。

**白天（随手记）**

1. 打开手机 AiDash → “记录”；
2. 打字，或拍便签/截图；
3. 点“AI 秘书处理”→ 预览安排（优先级/日期/理由）；
4. 逐条勾选或一键采纳 → “保存到云端”；
5. 明天的仪表盘就会带上这些安排。

**随时调整**

- 待办页：勾选完成、改内容/日期、增删；
- 倒计时页：增删改，剩余天数自动算；
- 设置页：改城市坐标、版块顺序（↑↓）和高度（px）、自动采纳开关。

---

## 本地电脑（可选）

```bash
cd scripts
pip install -r requirements.txt
python generate_image.py              # 手动生成图片（读 GitHub 数据）
python send_to_kindle.py --no-send    # 只生成 EPUB 预览
python send_to_kindle.py              # 生成并推送
```

不想用 GitHub Actions 的话，用 Windows 任务计划程序 / cron 定时跑
`send_to_kindle.py`（详见 docs/F-scheduling.md）。

---

## 常见问题速查

| 问题 | 解决方法 |
|---|---|
| 手机提示口令错误 401 | 手机口令与 Vercel `APP_PIN` 不一致 |
| AI 调用失败 502 | 检查 `DEEPSEEK_API_KEY`、余额、模型名 |
| 保存失败 502 | 检查 `GITHUB_TOKEN` 权限（Contents 读写）和 `GITHUB_REPO` 格式 |
| 收不到 Kindle 推送 | 国际账户 `@kindle.com`；发件邮箱加白名单；Kindle 连 Wi-Fi |
| Kindle 休眠显示广告 | 带特惠版，需在 amazon.com 移除广告 |
| 封面不是仪表盘 | 打开今天那本书后再休眠 |
| 页面打不开 | 等 Pages 更新 1~3 分钟；用 https 地址 |
| 图片太大 | 前端会自动压缩；仍失败就换个更小的图 |
| 想换 AI | Vercel 里 `AI_PROVIDER=openai` 并填 `OPENAI_API_KEY` |

详细排查见各部分的 docs 文档。

---

## 安全提示

- 所有 Token / 授权码只放在 Vercel 环境变量、GitHub Secrets 或本地未上传的配置文件里；
- `APP_PIN` 是唯一能调用你后端的口令，别设成 `1234` 这类常见数字；
- fine-grained Token 只授权 `aidash` 一个仓库、只勾 Contents 读写；
- 公开仓库里不写任何密钥；介意隐私可把仓库设为 Private（需自行确认免费版 Pages 可用）。
