// READ-ONLY smoke test of a deployed dashboard: signs in, looks at every screen, signs out. Changes no data.
//   E2E_PASSWORD=... BASE_URL=https://kgl-crm.onrender.com node smoke-live.mjs
import { chromium } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const BASE = process.env.BASE_URL;
const PASSWORD = process.env.E2E_PASSWORD;
const EMAIL = process.env.E2E_EMAIL || "admin@kamilightglobal.com";
if (!BASE || !PASSWORD) throw new Error("Set BASE_URL and E2E_PASSWORD");
const BROWSER =
  process.env.BROWSER_PATH ||
  ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"].find((p) => fs.existsSync(p));
const shots = path.join(os.tmpdir(), "kgl-live-shots");
fs.mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const page = await (await browser.newContext({ viewport: { width: 1366, height: 800 } })).newPage();
page.setDefaultTimeout(60000); // a free instance can take ~1 min to wake
const errors = [];
page.on("pageerror", (e) => errors.push("PAGEERROR " + e.message.slice(0, 140)));
page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });

let failed = 0;
async function step(name, fn) {
  try { await fn(); console.log("PASS  " + name); } catch (e) { failed++; console.log(`FAIL  ${name}\n      ${String(e.message).split("\n")[0]}`); }
}

await step("login page loads", async () => {
  await page.goto(BASE + "/login");
  await page.getByRole("button", { name: "Sign in" }).waitFor();
  await page.screenshot({ path: path.join(shots, "login.png") });
});
await step("wrong password is refused", async () => {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("Email or password is wrong.").waitFor();
});
await step("correct password opens the dashboard (test-mode banner shown until WhatsApp is connected)", async () => {
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  await page.screenshot({ path: path.join(shots, "dashboard.png") });
});
for (const [link, heading] of [["Customers", "Customers"], ["Segments", "Segments"], ["Campaigns", "Campaigns"]]) {
  await step(`${link} screen loads`, async () => {
    await page.getByRole("link", { name: link, exact: true }).first().click();
    await page.getByRole("heading", { name: heading, exact: true }).waitFor();
  });
}
await step("campaign builder opens with a live audience number", async () => {
  await page.goto(BASE + "/campaigns/new");
  await page.getByText("Will receive").waitFor();
  await page.screenshot({ path: path.join(shots, "campaign-new.png") });
});
await step("sign out returns to login", async () => {
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL(/\/login$/);
});
await browser.close();
console.log(errors.length ? "\nerrors:\n" + errors.join("\n") : "\nno server or page errors");
console.log("screenshots: " + shots);
process.exit(failed || errors.length ? 1 : 0);
