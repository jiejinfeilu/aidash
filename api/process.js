/* ================================================================
   POST /api/process —— AI 秘书分析
   入参：{ pin, text?, imageBase64? }
   - pin：与环境变量 APP_PIN 一致（4~6 位）
   - text：用户输入的文字（可选，与图片至少有一个）
   - imageBase64：图片的 base64 data URL（前端已压缩，≤4.2MB）
   返回：{ ok, summary, plan, todos, countdowns, notes, shopping, markdown, provider, model }
   ================================================================ */
var ai = require("./_lib/ai");
var http = require("./_lib/http");

/* 计算北京时间（Asia/Shanghai）的“YYYY-MM-DD（星期X）” */
function beijingToday() {
  var parts = {};
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric", month: "2-digit", day: "2-digit", weekday: "long"
  }).formatToParts(new Date()).forEach(function (p) {
    if (p.type !== "literal") { parts[p.type] = p.value; }
  });
  return parts.year + "-" + parts.month + "-" + parts.day + "（" + parts.weekday + "）";
}

/* 核心逻辑（独立出来便于本地测试） */
async function runProcess(input) {
  var env = input.env || process.env;

  /* 1. 口令校验 */
  var pin = String(input.pin || "");
  if (!env.APP_PIN || pin !== env.APP_PIN) {
    return { status: 401, json: { error: "口令错误" } };
  }

  /* 2. 参数校验 */
  var text = String(input.text || "").trim();
  var imageBase64 = String(input.imageBase64 || "");
  if (!text && !imageBase64) {
    return { status: 400, json: { error: "缺少文字或图片" } };
  }
  if (imageBase64 && !/^data:image\/(png|jpe?g|webp|gif|bmp);base64,/.test(imageBase64)) {
    return { status: 400, json: { error: "图片格式不支持（需要 base64 data URL）" } };
  }
  if (imageBase64.length > 4.4e6) {
    return { status: 413, json: { error: "图片太大（压缩后再试）" } };
  }

  /* 3. 选择服务商 */
  var providerName = String(env.AI_PROVIDER || "deepseek").toLowerCase();
  var provider = ai.PROVIDERS[providerName];
  if (!provider) {
    return { status: 400, json: { error: "AI_PROVIDER 只支持 deepseek 或 openai" } };
  }
  var apiKey = env[provider.envKey];
  if (!apiKey) {
    return { status: 500, json: { error: "未配置 " + provider.envKey + " 环境变量" } };
  }
  var model = env[provider.envModel] || provider.model;

  /* 4. 调用 AI */
  var messages = ai.buildSecretaryMessages({ text: text, imageBase64: imageBase64, today: beijingToday() });
  try {
    var content = await ai.chatCompletion({
      provider: providerName,
      apiKey: apiKey,
      model: model,
      messages: messages,
      timeoutMs: 55000
    });
    var parsed = ai.parseJsonContent(content);
    if (!parsed || typeof parsed !== "object") {
      return { status: 502, json: { error: "AI 返回无法解析为 JSON" } };
    }
    return {
      status: 200,
      json: { ok: true, provider: providerName, model: model, summary: parsed.summary || "", plan: parsed.plan || [], todos: parsed.todos || [], countdowns: parsed.countdowns || [], notes: parsed.notes || [], shopping: parsed.shopping || [], markdown: parsed.markdown || "" }
    };
  } catch (e) {
    return { status: 502, json: { error: "AI 调用失败：" + e.message } };
  }
}

/* Vercel 函数入口 */
module.exports = async function handler(req, res) {
  http.setCors(res);
  if (req.method === "OPTIONS") { res.status(200).end(); return; }
  if (req.method !== "POST") { res.status(405).json({ error: "仅支持 POST" }); return; }

  var body;
  try {
    body = JSON.parse(await http.readBody(req, 5 * 1024 * 1024));
  } catch (e) {
    res.status(400).json({ error: "请求体解析失败：" + e.message });
    return;
  }

  var result = await runProcess(body);
  res.status(result.status).json(result.json);
};

module.exports.runProcess = runProcess;
