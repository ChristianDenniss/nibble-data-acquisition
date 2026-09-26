import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(scriptDir, "..");
const profileDir = resolve(rootDir, ".profile");
const targetsPath = resolve(rootDir, "input/skip-targets.csv");

function parseCSV(text) {
  const rows = [];
  let row = [], value = "", quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '"' && quoted && text[i + 1] === '"') { value += '"'; i += 1; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) { row.push(value); value = ""; }
    else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(value); value = "";
      if (row.some((cell) => cell.trim())) rows.push(row);
      row = [];
    } else value += ch;
  }
  if (value || row.length) { row.push(value); rows.push(row); }
  const [headers, ...data] = rows;
  return data.map((cells) => Object.fromEntries(headers.map((h, i) => [h.trim(), (cells[i] ?? "").trim()])));
}

function norm(s) {
  return s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
}

function itemCore(s) {
  return norm(s).split(" ").filter((word) => !/^\d+$/.test(word) && !["inch", "inches", "small", "medium", "large"].includes(word)).join(" ");
}

const targets = parseCSV(await readFile(targetsPath, "utf8"));
const restaurants = new Map();
for (const target of targets) {
  const key = target.skip_url;
  if (!restaurants.has(key)) restaurants.set(key, []);
  restaurants.get(key).push(target);
}

const context = await chromium.launchPersistentContext(profileDir, {
  headless: true,
  viewport: { width: 1365, height: 900 },
});
const page = context.pages()[0] ?? await context.newPage();
const results = [];

try {
  for (const [url, restaurantTargets] of restaurants) {
    const restaurant = restaurantTargets[0].restaurant;
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.locator("body").waitFor({ state: "visible", timeout: 15000 });
      await page.waitForTimeout(2500);

      const menu = await page.evaluate(() => {
        const money = /\$\s*\d{1,4}(?:\.\d{2})?/g;
        const headings = [...document.querySelectorAll("h3,h4,h5,h6")];
        return headings.map((heading) => {
          const name = heading.innerText?.trim();
          if (!name) return null;
          let node = heading;
          for (let depth = 0; depth < 5 && node; depth += 1, node = node.parentElement) {
            const text = node.innerText?.replace(/\s+/g, " ").trim() ?? "";
            const prices = [...text.matchAll(money)].map((m) => Number(m[0].replace(/[^\d.]/g, "")));
            if (prices.length && text.length < 1200) return { name, text, prices };
          }
          return { name, text: name, prices: [] };
        }).filter(Boolean);
      });

      for (const target of restaurantTargets) {
        const wanted = norm(target.search_name);
        const core = itemCore(target.search_name);
        let candidates = menu.filter((entry) => {
          const name = norm(entry.name);
          const entryCore = itemCore(entry.name);
          return name === wanted || name.includes(wanted) || (core.length > 4 && (entryCore.includes(core) || core.includes(entryCore)));
        });
        if (target.expected_size) {
          const size = norm(target.expected_size);
          const sized = candidates.filter((entry) => norm(`${entry.name} ${entry.text}`).includes(size));
          if (sized.length) candidates = sized;
        }
        const priced = candidates.filter((entry) => entry.prices.length === 1);
        const uniquePrices = [...new Set(priced.map((entry) => entry.prices[0]))];
        if (candidates.length === 1 && uniquePrices.length === 1) {
          results.push({
            target_id: target.id,
            restaurant,
            item_name: candidates[0].name,
            price_cents: Math.round(uniquePrices[0] * 100),
            currency: "CAD",
            fulfillment_mode: "delivery",
            delivery_executor: "third_party",
            observed_at: new Date().toISOString(),
            source_url: url,
            status: "collected",
          });
        } else {
          results.push({
            target_id: target.id,
            restaurant,
            item_name: target.search_name,
            observed_at: new Date().toISOString(),
            source_url: url,
            status: candidates.length ? "ambiguous" : "not_found",
            candidates: candidates.slice(0, 10).map(({ name, prices }) => ({ name, prices })),
          });
        }
      }
    } catch (error) {
      for (const target of restaurantTargets) results.push({
        target_id: target.id,
        restaurant,
        item_name: target.search_name,
        observed_at: new Date().toISOString(),
        source_url: url,
        status: "collection_error",
        error: String(error),
      });
    }
  }
} finally {
  await context.close();
}

process.stdout.write(`${JSON.stringify({ collected_at: new Date().toISOString(), results })}\n`);
