/* ================================================================
   GitHub Contents API 封装：读取 / 写入仓库文件
   使用 fine-grained Token（环境变量 GITHUB_TOKEN），
   只授权 aidash 仓库的 Contents 读写权限即可。
   ================================================================ */
var https = require("https");

function api(method, pathname, bodyObj, timeoutMs) {
  var url = new URL("https://api.github.com" + pathname);
  var headers = {
    "Authorization": "Bearer " + (process.env.GITHUB_TOKEN || ""),
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "aidash-serverless",
    "Content-Type": "application/json"
  };
  return new Promise(function (resolve, reject) {
    var req = https.request(url, { method: method, headers: headers }, function (res) {
      var data = "";
      res.setEncoding("utf8");
      res.on("data", function (c) {
        data += c;
        if (data.length > 5e6) { req.destroy(new Error("GitHub 响应过大")); }
      });
      res.on("end", function () {
        var json = null;
        try { json = JSON.parse(data); } catch (e) {}
        resolve({ status: res.statusCode, json: json });
      });
    });
    req.setTimeout(timeoutMs || 20000, function () {
      req.destroy(new Error("GitHub API 超时"));
    });
    req.on("error", reject);
    if (bodyObj) { req.write(JSON.stringify(bodyObj)); }
    req.end();
  });
}

/* 读取仓库文件，返回 { status, json }；文件不存在时 status 为 404 */
function getFile(repo, branch, path) {
  var urlPath = "/repos/" + repo + "/contents/" + path + "?ref=" + encodeURIComponent(branch);
  return api("GET", urlPath);
}

/* 写入/更新仓库文件；sha 为当前文件 SHA（不存在时传 null） */
function putFile(repo, branch, path, content, sha, message) {
  var body = {
    message: message || "AiDash 数据更新",
    branch: branch,
    content: Buffer.from(content, "utf8").toString("base64")
  };
  if (sha) { body.sha = sha; }
  return api("PUT", "/repos/" + repo + "/contents/" + path, body);
}

module.exports = { getFile: getFile, putFile: putFile };
