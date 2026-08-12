/* ================================================================
   AI 调用封装：DeepSeek（默认）/ OpenAI 双模式
   两者都是 OpenAI 兼容格式，识别图片时把 base64 图片作为
   image_url 传入（DeepSeek V4 与 OpenAI 视觉模型均支持）。
   ================================================================ */
var https = require("https");

/* 两家服务商的配置：base 地址、请求路径、默认模型、环境变量名 */
var PROVIDERS = {
  deepseek: {
    base: "https://api.deepseek.com",
    chatPath: "/chat/completions",
    model: "deepseek-chat",
    envKey: "DEEPSEEK_API_KEY",
    envModel: "DEEPSEEK_MODEL"
  },
  openai: {
    base: "https://api.openai.com",
    chatPath: "/v1/chat/completions",
    model: "gpt-4o-mini",
    envKey: "OPENAI_API_KEY",
    envModel: "OPENAI_MODEL"
  }
};

/* 发起 HTTPS POST，返回解析后的 JSON；非 2xx 时抛出错误 */
function httpsJsonPost(urlStr, headers, body, timeoutMs) {
  return new Promise(function (resolve, reject) {
    var url = new URL(urlStr);
    var req = https.request(url, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, headers)
    }, function (res) {
      var data = "";
      res.setEncoding("utf8");
      res.on("data", function (c) {
        data += c;
        if (data.length > 5e6) { req.destroy(new Error("响应过大")); }
      });
      res.on("end", function () {
        var json = null;
        try { json = JSON.parse(data); } catch (e) {}
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(json || {});
        } else {
          var msg = (json && json.error && (json.error.message || JSON.stringify(json.error))) || ("HTTP " + res.statusCode);
          reject(new Error(msg));
        }
      });
    });
    req.setTimeout(timeoutMs || 60000, function () {
      req.destroy(new Error("AI 请求超时"));
    });
    req.on("error", reject);
    req.write(JSON.stringify(body));
    req.end();
  });
}

/* 组装“秘书”角色的消息：系统提示 + 用户文字 + 可选图片 */
function buildSecretaryMessages(input) {
  var today = input.today || "";
  var system =
    "你是我的资深私人助理（秘书）。请把用户随手记录的文字和图片（手写便签、屏幕截图、票据、备忘录等）理解清楚，像贴心秘书一样给出安排，而不是机械分类。\n" +
    "\n" +
    "工作要求：\n" +
    "1. 从信息中提炼“可执行事项”放入 todos，判断优先级（高/中/低），并给出建议完成日期 dueDate（格式 YYYY-MM-DD；仅当信息中出现日期、截止日或相对时间词（如“周六”“下周一”“月底”）时，根据今天日期推算填写；否则填空字符串），每条都要有 reason（一句话说明为什么这样安排）。\n" +
    "2. 有明确日期的事件（如“10月3日参加婚礼”）要同时放入 countdowns（name 用事件名，date 用 YYYY-MM-DD）和 todos。\n" +
    "3. 纯想法、灵感、知识、备忘放进 notes，tags 给 1~3 个简短标签；买东西的需求放进 shopping。\n" +
    "4. plan 给出“今天应该优先做的事”，按优先级和截止日期排序，每项一句话。\n" +
    "5. 图片中的文字必须全部读取并纳入分析；不要编造图片里没有的信息；如果图片和文字都有，以两者结合为准。\n" +
    "\n" +
    "输出要求：\n" +
    "- 只输出一个合法 JSON 对象，不要输出任何其他文字。\n" +
    "- JSON 结构固定为：\n" +
    "{\n" +
    "  \"summary\": \"一句话总结这条信息\",\n" +
    "  \"plan\": [\"今天优先：…\", \"…\"],\n" +
    "  \"todos\": [{\"text\": \"…\", \"priority\": \"高|中|低\", \"dueDate\": \"YYYY-MM-DD 或空字符串\", \"reason\": \"…\"}],\n" +
    "  \"countdowns\": [{\"name\": \"…\", \"date\": \"YYYY-MM-DD\"}],\n" +
    "  \"notes\": [{\"text\": \"…\", \"tags\": [\"标签1\", \"标签2\"]}],\n" +
    "  \"shopping\": [{\"text\": \"…\"}],\n" +
    "  \"markdown\": \"把这条信息整理成适合存档的中文 Markdown（包含待办清单、倒计时、笔记、购物清单）\"\n" +
    "}\n" +
    "\n" +
    "今天是：" + today;

  var content = [];
  if (input.text) { content.push({ type: "text", text: input.text }); }
  if (input.imageBase64) { content.push({ type: "image_url", image_url: { url: input.imageBase64 } }); }
  if (!content.length) { content.push({ type: "text", text: "（只有图片，请仔细识别图片内容）" }); }

  return [
    { role: "system", content: system },
    { role: "user", content: content }
  ];
}

/* 调用 Chat Completions，返回模型输出的文本 */
async function chatCompletion(options) {
  var p = PROVIDERS[options.provider];
  if (!p) { throw new Error("未知 AI_PROVIDER：" + options.provider); }
  var payload = {
    model: options.model || p.model,
    messages: options.messages,
    temperature: 0.3,
    max_tokens: 4096,
    response_format: { type: "json_object" }
  };
  var res = await httpsJsonPost(
    p.base + p.chatPath,
    { "Authorization": "Bearer " + options.apiKey },
    payload,
    options.timeoutMs
  );
  var choice = res.choices && res.choices[0];
  var content = choice && choice.message && choice.message.content;
  if (!content) {
    throw new Error("AI 返回为空（" + (res.error ? JSON.stringify(res.error) : "未知错误") + "）");
  }
  return content;
}

/* 尽量从模型输出中解析出 JSON（支持纯 JSON / 代码块 / 前后有杂文） */
function parseJsonContent(content) {
  if (!content) { return null; }
  var s = String(content).trim();
  try { return JSON.parse(s); } catch (e) {}
  var fence = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) {
    try { return JSON.parse(fence[1].trim()); } catch (e2) {}
  }
  var start = s.indexOf("{");
  var end = s.lastIndexOf("}");
  if (start >= 0 && end > start) {
    try { return JSON.parse(s.slice(start, end + 1)); } catch (e3) {}
  }
  return null;
}

module.exports = {
  PROVIDERS: PROVIDERS,
  buildSecretaryMessages: buildSecretaryMessages,
  chatCompletion: chatCompletion,
  parseJsonContent: parseJsonContent,
  httpsJsonPost: httpsJsonPost
};
