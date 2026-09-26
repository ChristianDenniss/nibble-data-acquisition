import { chromium } from "playwright";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const profileDir = resolve(scriptDir, "../.profile");

const context = await chromium.launchPersistentContext(profileDir, {
  headless: false,
});

const page = context.pages()[0] ?? await context.newPage();
await page.goto("https://www.skipthedishes.com/");

const terminal = createInterface({ input: stdin, output: stdout });
await terminal.question(
  "Sign in normally and set the Fredericton delivery address in the browser, then press Enter here. "
);
terminal.close();

await context.close();
console.log("Skip browser profile saved locally. Do not share or commit the .profile folder.");
