// 用一般 Playwright Chromium（無任何偽裝套件）測試健保署頁面是否可在 CI 取得。
// Cloudflare managed challenge 對真實瀏覽器常會自動放行；若仍要求互動驗證則如實失敗。
import { chromium } from "playwright";
import fs from "node:fs";

const targets = [
  { name: "list", url: "https://www.nhi.gov.tw/ch/lp-3258-1.html" },
  { name: "list-p1", url: "https://www.nhi.gov.tw/ch/lp-3258-1.html?pi=1&ps=60" },
  { name: "rss", url: "https://www.nhi.gov.tw/ch/rss-3258-1.xml" },
];

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  locale: "zh-TW",
  timezoneId: "Asia/Taipei",
  viewport: { width: 1366, height: 900 },
});
const page = await ctx.newPage();

fs.mkdirSync("cache/live", { recursive: true });
let anyOk = false;

for (const t of targets) {
  try {
    const resp = await page.goto(t.url, { waitUntil: "domcontentloaded", timeout: 45000 });
    // 等 Cloudflare challenge 自動解（最多 40 秒）
    for (let i = 0; i < 20; i++) {
      const title = await page.title();
      if (!/just a moment/i.test(title)) break;
      await page.waitForTimeout(2000);
    }
    const title = await page.title();
    const html = await page.content();
    const blocked = /just a moment/i.test(title) || html.includes("cf_chl_opt");
    console.log(`${t.name}: HTTP ${resp?.status()} | title="${title.slice(0, 60)}" | ${blocked ? "❌ 仍被挑戰頁擋住" : "✅ 取得內容"} | ${html.length} bytes`);
    if (!blocked && html.length > 5000) {
      const fname = t.url.split("/ch/")[1].replace(/[?&=]/g, "_");
      fs.writeFileSync(`cache/live/${fname}`, html);
      anyOk = true;
    }
  } catch (e) {
    console.log(`${t.name}: 失敗 ${String(e).slice(0, 120)}`);
  }
}

await browser.close();
console.log(anyOk ? "RESULT: BROWSER_OK" : "RESULT: BROWSER_BLOCKED");
process.exit(anyOk ? 0 : 1);
