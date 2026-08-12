/* ================================================================
   AiDash 前端配置（B 部分）
   部署后请修改下面两个地址；也可以在手机 App 的
   “设置 → 连接”里填写，App 内的填写会覆盖这里的默认值。
   ================================================================ */
window.AIDASH_CONFIG = {
  /* Vercel 后端地址：C 部分部署完成后，形如 https://aidash-xxxx.vercel.app */
  API_BASE: "https://aidash.vercel.app",

  /* GitHub 数据 raw 地址：改成【你的 GitHub 用户名】和仓库名 */
  RAW_BASE: "https://raw.githubusercontent.com/jiejinfeilu/aidash/main",

  /* 默认设置（可在 App “设置”里修改） */
  DEFAULT_SETTINGS: {
    city: "温州",
    lat: "27.99",
    lon: "120.70",
    autoAdopt: false
  },

  /* 默认版块布局（与 D 部分 generate_image.py 保持一致，可在 App 里改） */
  DEFAULT_LAYOUT: {
    order: ["header", "weather", "feeds", "countdown", "todo", "notes", "quote"],
    heights: {
      weather: 170,
      feeds: 300,
      countdown: 150,
      todo: 240,
      notes: 180,
      quote: 90
    }
  }
};
