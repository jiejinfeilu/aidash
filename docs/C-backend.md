# AiDash — C 部分：Vercel 后端部署步骤

> 本部分包含：`api/process.js`（AI 秘书）、`api/save.js`（写回 GitHub）、`api/_lib/`（共用封装）、`vercel.json`、`.env.example`。

## 1. 先看懂两个接口

| 接口 | 作用 | 关键入参 | 返回 |
|---|---|---|---|
| `POST /api/process` | AI 秘书分析文字+图片 | `pin`、`text`、`imageBase64` | `summary / plan / todos / countdowns / notes / shopping / markdown` |
| `POST /api/save` | 合并数据写回 GitHub | `pin`、`data`、`markdown?` | `{ ok, updatedAt }` |

两个接口都要求 `pin` 与 Vercel 环境变量 `APP_PIN` 一致，否则返回 401。

## 2. 上传到 GitHub 仓库

1. 打开你的 `aidash` 仓库 → Code → Add file → **Upload files**。
2. 把本机 `aidash` 文件夹里的以下内容拖进去：
   - `api/` 整个文件夹（含 `process.js`、`save.js`、`_lib/`）
   - `vercel.json`
   - `.env.example`（只含变量名，不含真实密钥，可上传）
3. 填写提交说明（如 `add backend`）→ Commit changes。

> 注意：真实密钥**不要**写进任何文件。`.env.example` 只是模板。

## 3. 在 Vercel 部署

1. 打开 https://vercel.com ，用 GitHub 账号登录。
2. Add New → **Project** → Import `aidash` 仓库。
3. 配置：
   - Framework Preset：**Other**
   - Build Command / Output Directory：**留空**（纯 API，无前端构建）
   - Root Directory：**留空**
4. 在 **Environment Variables** 里添加 9 个变量：

| 变量 | 填写 |
|---|---|
| AI_PROVIDER | `deepseek` |
| DEEPSEEK_API_KEY | 你的 DeepSeek Key |
| DEEPSEEK_MODEL | `deepseek-chat` |
| OPENAI_API_KEY | 留空（用 OpenAI 时再填） |
| OPENAI_MODEL | `gpt-4o-mini` |
| GITHUB_TOKEN | fine-grained Token（见 A 部分第 4.1 节） |
| GITHUB_REPO | `你的用户名/aidash` |
| GITHUB_BRANCH | `main` |
| APP_PIN | 你自己定的 4~6 位口令（手机端要填同一个） |

5. 点 **Deploy**。部署完成后会得到地址，形如：
   `https://aidash-xxxxx.vercel.app`
6. 之后每次仓库更新，Vercel 会自动重新部署。

## 4. 验证接口（部署后用电脑测试）

### 4.1 口令错误 → 应返回 401

```bash
curl -X POST https://你的项目.vercel.app/api/process \
  -H "Content-Type: application/json" \
  -d '{"pin":"0000","text":"周六前把房租转给房东"}'
```

### 4.2 正常调用 → 应返回 AI 秘书 JSON

```bash
curl -X POST https://你的项目.vercel.app/api/process \
  -H "Content-Type: application/json" \
  -d '{"pin":"你的口令","text":"周六前把房租转给房东，10月3日参加婚礼"}'
```

预期 `todos` 里出现“把房租转给房东”且 `dueDate` 为最近的周六，`countdowns` 里出现“参加婚礼”。

### 4.3 保存测试（会把仓库里的 data.json 初始化）

```bash
curl -X POST https://你的项目.vercel.app/api/save \
  -H "Content-Type: application/json" \
  -d '{"pin":"你的口令","data":{"todos":[],"countdowns":[],"notes":[],"shopping":[],"layout":{},"settings":{}}}'
```

成功后到仓库里刷新，能看到 `data.json` 和 `data.md` 两个文件被创建。

## 5. 前端对接

1. 手机 App → 设置 → 连接：
   - 后端地址填：`https://aidash-xxxxx.vercel.app`
   - GitHub 数据地址填：`https://raw.githubusercontent.com/你的用户名/aidash/main`
   - 口令填：与 `APP_PIN` 相同
2. 点“保存连接”，然后回“记录”页测试。

## 6. 常见问题

- **401 口令错误**：手机端填的口令与 Vercel 环境变量 `APP_PIN` 不一致。
- **502 AI 调用失败**：`DEEPSEEK_API_KEY` 没填、余额不足，或 DeepSeek 官网模型名变更（在 Vercel 环境变量里改 `DEEPSEEK_MODEL`）。
- **502 GitHub 写入失败**：Token 权限不足（需要 Contents 读写）、Token 过期，或 `GITHUB_REPO` 写错（格式 `用户名/仓库名`）。
- **图片太大**：前端已自动压缩；若仍报错，说明图片质量/尺寸超限，压缩参数在 `web/index.html` 的 `fileToDataURL` 里。
- **想用 OpenAI**：把 `AI_PROVIDER` 改成 `openai`，填上 `OPENAI_API_KEY`；注意国内网络需要代理，费用高于 DeepSeek。
- **本地测试**：可用 `node` 直接跑 `api/process.js` 的 `runProcess`（见代码注释），但正常使用请以 Vercel 线上环境为准。
