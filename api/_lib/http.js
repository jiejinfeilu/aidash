/* ================================================================
   Vercel 函数共用工具：CORS 与请求体读取
   ================================================================ */

/* 设置跨域响应头：前端部署在 GitHub Pages，域名与 Vercel 不同 */
function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

/* 读取请求体文本，超过 limit 字节则报错（Vercel 免费版函数体上限约 4.5MB） */
function readBody(req, limit) {
  return new Promise(function (resolve, reject) {
    var size = 0;
    var chunks = [];
    req.on("data", function (c) {
      size += c.length;
      if (size > limit) {
        reject(new Error("请求体超过限制"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", function () {
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
    req.on("error", reject);
  });
}

module.exports = { setCors: setCors, readBody: readBody };
