/* ================================================================
   POST /api/save —— 把手机端数据合并写入 GitHub 仓库
   入参：{ pin, data, markdown? }
   - data：完整数据对象 { version, updatedAt, todos, countdowns,
     notes, shopping, layout, settings }
   - markdown：最近一次 AI 秘书的 Markdown（可选，写入 data.md）
   流程：读 data.json → 合并去重 → 写回 data.json 和 data.md；
   若遇 409 冲突（并发提交），自动重读重试一次。
   ================================================================ */
var github = require("./_lib/github");
var http = require("./_lib/http");

var DATA_FILE = "data.json";
var MD_FILE = "data.md";
var DEFAULT_ORDER = ["header", "weather", "feeds", "countdown", "todo", "notes", "quote"];

function nowISO() { return new Date().toISOString(); }

/* 合并数据：按 text / name+date 去重，新数据覆盖旧字段 */
function mergeData(existing, incoming, now) {
  now = now || nowISO();
  var old = existing && typeof existing === "object" ? existing : {};
  var inc = incoming && typeof incoming === "object" ? incoming : {};

  function mergeList(oldArr, newArr, keyFn, makeItem) {
    var out = [];
    var seen = {};
    (Array.isArray(oldArr) ? oldArr : []).forEach(function (item) {
      var k = keyFn(item);
      var ni = null;
      (Array.isArray(newArr) ? newArr : []).forEach(function (x) {
        if (keyFn(x) === k) { ni = x; }
      });
      if (ni) { seen[k] = true; out.push(makeItem(ni, item, now)); }
      else { out.push(item); }
    });
    (Array.isArray(newArr) ? newArr : []).forEach(function (ni) {
      var k = keyFn(ni);
      if (!seen[k]) { seen[k] = true; out.push(makeItem(ni, null, now)); }
    });
    return out;
  }

  var todos = mergeList(old.todos, inc.todos,
    function (t) { return String(t.text || ""); },
    function (ni, oi) {
      return {
        text: String(ni.text || ""),
        priority: ["高", "中", "低"].indexOf(ni.priority) >= 0 ? ni.priority : (oi && oi.priority) || "中",
        dueDate: ni.dueDate != null ? String(ni.dueDate) : (oi ? oi.dueDate : ""),
        done: typeof ni.done === "boolean" ? ni.done : (oi ? !!oi.done : false),
        source: ni.source || (oi && oi.source) || "manual",
        createdAt: (oi && oi.createdAt) || ni.createdAt || now
      };
    }
  ).filter(function (t) { return t.text; });

  var countdowns = mergeList(old.countdowns, inc.countdowns,
    function (c) { return String(c.name || "") + "|" + String(c.date || ""); },
    function (ni) { return { name: String(ni.name || ""), date: String(ni.date || "") }; }
  ).filter(function (c) { return c.name && c.date; });

  var notes = mergeList(old.notes, inc.notes,
    function (n) { return String(n.text || ""); },
    function (ni, oi) {
      return {
        text: String(ni.text || ""),
        tags: Array.isArray(ni.tags) ? ni.tags.map(String) : ((oi && oi.tags) || []),
        createdAt: (oi && oi.createdAt) || ni.createdAt || now
      };
    }
  ).filter(function (n) { return n.text; });

  var shopping = mergeList(old.shopping, inc.shopping,
    function (s) { return String(s.text || ""); },
    function (ni) { return { text: String(ni.text || ""), createdAt: ni.createdAt || now }; }
  ).filter(function (s) { return s.text; });

  var layout = (inc.layout && typeof inc.layout === "object")
    ? {
        order: (Array.isArray(inc.layout.order) && inc.layout.order.length) ? inc.layout.order.slice() : ((old.layout && old.layout.order) || DEFAULT_ORDER),
        heights: Object.assign({}, (old.layout && old.layout.heights) || {}, inc.layout.heights || {})
      }
    : (old.layout || { order: DEFAULT_ORDER, heights: {} });

  var settings = Object.assign({}, old.settings || {}, inc.settings || {});

  return {
    version: 1,
    updatedAt: inc.updatedAt || now,
    todos: todos, countdowns: countdowns, notes: notes, shopping: shopping,
    layout: layout, settings: settings
  };
}

/* 根据 data 生成 data.md（可附带最近一次 AI 秘书 Markdown） */
function buildMarkdown(data, aiMarkdown) {
  data = data || {};
  var L = [];
  L.push("# AiDash 生活记录");
  L.push("");
  L.push("> 最近更新：" + (data.updatedAt || nowISO()));
  L.push("");

  var md = aiMarkdown && String(aiMarkdown).trim();
  if (md) {
    L.push("## 秘书安排（最近一次）");
    L.push("");
    L.push(md);
    L.push("");
  }

  L.push("## 待办");
  L.push("");
  var todos = Array.isArray(data.todos) ? data.todos : [];
  if (!todos.length) { L.push("_暂无_"); }
  todos.forEach(function (t) {
    var tag = "";
    if (t.priority || t.dueDate) {
      tag = "（" + (t.priority || "中") + (t.dueDate ? "，截止 " + t.dueDate : "") + "）";
    }
    L.push("- [" + (t.done ? "x" : " ") + "] " + tag + String(t.text || ""));
  });
  L.push("");

  L.push("## 倒计时");
  L.push("");
  var counts = Array.isArray(data.countdowns) ? data.countdowns : [];
  if (!counts.length) { L.push("_暂无_"); }
  counts.forEach(function (c) { L.push("- " + (c.name || "") + "：" + (c.date || "")); });
  L.push("");

  L.push("## 笔记");
  L.push("");
  var notes = Array.isArray(data.notes) ? data.notes : [];
  if (!notes.length) { L.push("_暂无_"); }
  notes.forEach(function (n) {
    L.push("- " + (n.text || "") + (Array.isArray(n.tags) && n.tags.length ? " #" + n.tags.join(" #") : ""));
  });
  L.push("");

  L.push("## 购物清单");
  L.push("");
  var shop = Array.isArray(data.shopping) ? data.shopping : [];
  if (!shop.length) { L.push("_暂无_"); }
  shop.forEach(function (s) { L.push("- " + (s.text || "")); });

  return L.join("\n") + "\n";
}

/* 核心逻辑（独立出来便于本地测试） */
async function runSave(input) {
  var env = input.env || process.env;

  /* 1. 口令校验 */
  var pin = String(input.pin || "");
  if (!env.APP_PIN || pin !== env.APP_PIN) {
    return { status: 401, json: { error: "口令错误" } };
  }

  /* 2. 配置校验 */
  var repo = String(env.GITHUB_REPO || "").trim();
  var branch = String(env.GITHUB_BRANCH || "main").trim();
  var token = String(env.GITHUB_TOKEN || "").trim();
  if (!repo || !token) {
    return { status: 500, json: { error: "未配置 GITHUB_REPO / GITHUB_TOKEN 环境变量" } };
  }
  if (!input.data || typeof input.data !== "object") {
    return { status: 400, json: { error: "缺少 data 字段" } };
  }

  /* 3. 读取现有 data.json */
  var existing = null;
  var sha = null;
  try {
    var r = await github.getFile(repo, branch, DATA_FILE);
    if (r.status === 404) {
      existing = null;
      sha = null;
    } else if (r.status === 200) {
      existing = JSON.parse(Buffer.from(r.json.content, "base64").toString("utf8"));
      sha = r.json.sha;
    } else {
      return { status: 502, json: { error: "GitHub 读取 data.json 失败（HTTP " + r.status + "）" } };
    }
  } catch (e) {
    return { status: 502, json: { error: "GitHub 读取失败：" + e.message } };
  }

  var now = nowISO();
  var merged = mergeData(existing, input.data, now);

  /* 4. 读取 data.md 的 SHA（不存在则新建） */
  var mdSha = null;
  try {
    var mr = await github.getFile(repo, branch, MD_FILE);
    if (mr.status === 200) { mdSha = mr.json.sha; }
  } catch (e) { /* 读取失败就按新建处理，PUT 时会报错 */ }

  var md = buildMarkdown(merged, input.markdown);

  /* 5. 写入两个文件；409 冲突时重试一次 */
  try {
    var r1 = await github.putFile(repo, branch, DATA_FILE, JSON.stringify(merged, null, 2), sha, "AiDash 更新数据 " + merged.updatedAt);

    if (r1.status === 409 && sha) {
      var r2 = await github.getFile(repo, branch, DATA_FILE);
      if (r2.status === 200) {
        var existing2 = JSON.parse(Buffer.from(r2.json.content, "base64").toString("utf8"));
        var merged2 = mergeData(existing2, input.data, now);
        var r3 = await github.putFile(repo, branch, DATA_FILE, JSON.stringify(merged2, null, 2), r2.json.sha, "AiDash 更新数据（重试） " + merged2.updatedAt);
        if (r3.status === 409) {
          return { status: 409, json: { error: "并发冲突，请稍后重试" } };
        }
        var md2 = buildMarkdown(merged2, input.markdown);
        var mdSha2 = mdSha;
        var mr2 = await github.getFile(repo, branch, MD_FILE);
        if (mr2.status === 200) { mdSha2 = mr2.json.sha; }
        await github.putFile(repo, branch, MD_FILE, md2, mdSha2, "AiDash 更新 Markdown " + merged2.updatedAt);
        return { status: 200, json: { ok: true, updatedAt: merged2.updatedAt } };
      }
    }

    if (r1.status < 200 || r1.status >= 300) {
      return { status: 502, json: { error: "GitHub 写入 data.json 失败（HTTP " + r1.status + "）" } };
    }

    var r4 = await github.putFile(repo, branch, MD_FILE, md, mdSha, "AiDash 更新 Markdown " + merged.updatedAt);
    if (r4.status < 200 || r4.status >= 300) {
      return { status: 502, json: { error: "GitHub 写入 data.md 失败（HTTP " + r4.status + "）" } };
    }

    return { status: 200, json: { ok: true, updatedAt: merged.updatedAt } };
  } catch (e) {
    return { status: 502, json: { error: "GitHub 写入失败：" + e.message } };
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

  var result = await runSave(body);
  res.status(result.status).json(result.json);
};

module.exports.runSave = runSave;
module.exports.mergeData = mergeData;
module.exports.buildMarkdown = buildMarkdown;
