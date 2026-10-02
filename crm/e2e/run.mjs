// End-to-end browser test of the KGL dashboard against a FRESH throwaway database.
//   1. start the backend with a new SQLite DB (RUN_WORKER=true, ADMIN_PASSWORD=e2e-pass-123) and the Vite dev server
//   2. cd crm/e2e && npm install && npm test
// Never point this at a real database: it creates, edits and deletes customers.
import { chromium } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || "http://localhost:5173";
const PASSWORD = process.env.E2E_PASSWORD || "e2e-pass-123";
const EMAIL = process.env.E2E_EMAIL || "admin@kamilightglobal.com";
const BROWSER =
  process.env.BROWSER_PATH ||
  ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"].find((p) => fs.existsSync(p));
const shots = path.join(os.tmpdir(), "kgl-e2e-shots");
fs.mkdirSync(shots, { recursive: true });

// ---- test data: KGL-style sheet, with a duplicate, a bad number and a blank number ----
const rows = ["S/N,NAME OF CUSTOMER,PHONE NUMBER ,EMAIL,REMARK"];
const names = ["Ada", "Bayo", "Chika", "Dele", "Efe", "Funmi", "Gbenga", "Halima", "Ifeanyi", "Jide"];
for (let i = 0; i < 60; i++) {
  const remark = i < 6 ? "existing customer" : i < 10 ? "past customer" : "potential c";
  rows.push(`${i + 1},${names[i % 10]} Tester${i},0803${String(1000000 + i)},${i % 5 === 0 ? `t${i}@example.com` : ""},${remark}`);
}
rows.push("61,Ada Tester0 (again),+234 803 1000000,,existing customer"); // duplicate of row 1
rows.push("62,Broken Number,0803123,,potential c"); // bad phone
rows.push("63,No Phone,,,potential c"); // blank phone
const csvPath = path.join(os.tmpdir(), "kgl-e2e-list.csv");
fs.writeFileSync(csvPath, rows.join("\n"));

// ---- tiny harness ----
const results = [];
const consoleErrors = [];
const badRequests = [];
async function step(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`PASS  ${name}`);
  } catch (e) {
    results.push({ name, ok: false, err: String(e.message || e).split("\n")[0] });
    console.log(`FAIL  ${name}\n      ${String(e.message || e).split("\n")[0]}`);
  }
}
const eq = (a, b, what) => { if (a !== b) throw new Error(`${what}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); };
const ok = (c, what) => { if (!c) throw new Error(what); };
async function until(fn, what, timeout = 8000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try { last = await fn(); if (last) return last; } catch (e) { last = e; }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`timed out waiting for: ${what}${last instanceof Error ? " (" + last.message.split("\n")[0] + ")" : ""}`);
}

const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 800 }, acceptDownloads: true });
const page = await ctx.newPage();
page.setDefaultTimeout(8000);
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 160)); });
page.on("pageerror", (e) => consoleErrors.push("PAGEERROR " + e.message.slice(0, 160)));
page.on("response", (r) => {
  const s = r.status(), u = r.url();
  if (u.includes("/api/") && s >= 400) badRequests.push(`${s} ${r.request().method()} ${u.replace(BASE, "")}`);
});
page.on("dialog", (d) => d.accept("Price too high"));

const main = page.locator("main");
const countText = async () => (await main.getByText(/^[\d,]+ customers?$/).first().innerText()).replace(/ customers?$/, "");
const waitCount = (n) => until(async () => (await countText()) === String(n), `customer count to be ${n}`);
const openFilters = async () => {
  if (!(await page.getByLabel("At least this many shipments").isVisible())) await page.getByRole("button", { name: /^Filters/ }).click();
};
const chip = (name) => page.getByRole("button", { name, exact: true });

// ============ AUTH ============
await step("logged-out visit to /customers redirects to login", async () => {
  await page.goto(BASE + "/customers");
  await until(async () => page.url().endsWith("/login"), "redirect to /login");
});
await step("wrong password shows an error and stays on login", async () => {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill("nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("Email or password is wrong.").waitFor();
  ok(page.url().endsWith("/login"), "should still be on /login");
});
await step("correct password signs in and shows dashboard + test-mode banner", async () => {
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  await page.getByText("Test mode.").waitFor();
});
await step("empty customer list shows the friendly empty state", async () => {
  await page.getByRole("link", { name: "Customers" }).first().click();
  await page.getByText("No customers yet.").waitFor();
});

// ============ IMPORT ============
await step("import dialog: disabled without a file; imports a KGL-style sheet and reports problems", async () => {
  await page.getByRole("button", { name: "Import list" }).click();
  const dlg = page.getByRole("dialog");
  ok(await dlg.getByRole("button", { name: "Import", exact: true }).isDisabled(), "Import should be disabled without a file");
  await page.locator("#import-file").setInputFiles(csvPath);
  await dlg.getByRole("checkbox").check();
  await dlg.getByRole("button", { name: "Import", exact: true }).click();
  await dlg.getByText(/new customers added/).waitFor();
  const t = (await dlg.innerText()).replace(/\n/g, " ");
  ok(/60\s*new customers added/.test(t), "expected 60 created: " + t.slice(0, 140));
  ok(/3\s*rows skipped/.test(t), "expected 3 skipped: " + t.slice(0, 180));
  await dlg.getByText(/Show problems/).click();
  await dlg.getByRole("button", { name: "Done" }).click();
});
await step("list shows 60 customers; 50 rows on page 1; pagination works", async () => {
  await waitCount(60);
  eq(await page.locator("tbody tr").count(), 50, "rows on page 1");
  await main.getByText("Page 1 of 2").waitFor();
  await main.getByRole("button", { name: "Next" }).click();
  await main.getByText("Page 2 of 2").waitFor();
  await until(async () => (await page.locator("tbody tr").count()) === 10, "10 rows on page 2");
  await main.getByRole("button", { name: "Previous" }).click();
  await main.getByText("Page 1 of 2").waitFor();
});
await step("imported statuses come from the Remark column (6 booked, 4 dormant)", async () => {
  await page.getByRole("button", { name: /^Filters/ }).click();
  await chip("Booked").click();
  await waitCount(6);
  await chip("Booked").click();
  await chip("Dormant").click();
  await waitCount(4);
  await chip("Dormant").click();
  await waitCount(60);
});

// ============ SEARCH / FILTERS / SORT / EXPORT ============
await step("search is live (debounced) and case-insensitive; clears back", async () => {
  await page.locator("#search").fill("tester17");
  await waitCount(1);
  await page.locator("#search").fill("zzznomatch");
  await main.getByText("No customers match these filters.").waitFor();
  await page.locator("#search").fill("");
  await waitCount(60);
});
await step("search by phone number fragment", async () => {
  await page.locator("#search").fill("1000005");
  await waitCount(1);
  await page.locator("#search").fill("");
  await waitCount(60);
});
await step("filters sync to the URL, survive reload, and Clear resets", async () => {
  await chip("Booked").click();
  await waitCount(6);
  ok(page.url().includes("f="), "URL should carry the filter");
  await page.reload();
  await waitCount(6);
  await page.getByRole("button", { name: "Filters (1)" }).waitFor();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await waitCount(60);
  ok(!page.url().includes("f="), "URL filter should be removed after Clear");
});
await step("number filters narrow the list and release again", async () => {
  await openFilters();
  await page.getByLabel("At least this many shipments").fill("1");
  await waitCount(0);
  await page.getByLabel("At least this many shipments").fill("");
  await waitCount(60);
  await page.getByLabel("Not shipped for (days)").fill("30");
  await waitCount(0); // nobody has shipped yet
  await page.getByLabel("Not shipped for (days)").fill("");
  await waitCount(60);
});
await step("sort by name puts A before Z", async () => {
  await page.locator("#sort").selectOption("name");
  await until(async () => (await page.locator("tbody tr").first().locator("td").first().innerText()).trim().startsWith("Ada"), "first row to start with Ada");
});
await step("Export CSV downloads all 60 customers with a header row", async () => {
  const [dl] = await Promise.all([page.waitForEvent("download"), main.getByRole("button", { name: "Export CSV" }).click()]);
  const text = fs.readFileSync(await dl.path(), "utf8");
  ok(text.startsWith("id,name,phone"), "csv header missing");
  eq(text.trim().split("\n").length, 61, "csv lines (60 + header)");
});

// ============ ADD CUSTOMER ============
await step("add customer: duplicate and invalid numbers are refused with clear messages", async () => {
  await page.getByRole("button", { name: "Add customer" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.locator("#add-name").fill("Dup Person");
  await dlg.locator("#add-phone").fill("08031000000");
  await dlg.getByRole("button", { name: "Add customer" }).click();
  await dlg.getByText(/already belongs to/).waitFor();
  await dlg.locator("#add-phone").fill("123");
  await dlg.getByRole("button", { name: "Add customer" }).click();
  await dlg.getByText(/isn't a valid phone number/).waitFor();
});
await step("Escape closes a dialog; a valid new customer opens its profile", async () => {
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Add customer" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.locator("#add-name").fill("Zainab Newbuyer");
  await dlg.locator("#add-phone").fill("0805 555 1212");
  await dlg.locator("#add-city").fill("Ikeja");
  await dlg.locator("#add-type").selectOption("online_seller");
  await dlg.getByRole("button", { name: "Add customer" }).click();
  await page.getByRole("heading", { name: "Zainab Newbuyer" }).waitFor();
  await page.getByText("New enquiry").first().waitFor();
});

// ============ PROFILE ============
await step("profile: edited details save and persist after reload", async () => {
  await page.locator("#p-city").fill("Lekki");
  await page.locator("#p-goods").fill("phone accessories");
  await page.locator("#p-routes").fill("china-air, lagos-uk");
  await page.getByRole("button", { name: "Save details" }).click();
  await page.getByText("Details saved").waitFor();
  await page.reload();
  await page.locator("#p-city").waitFor();
  eq(await page.locator("#p-city").inputValue(), "Lekki", "city");
  eq(await page.locator("#p-routes").inputValue(), "china-air, lagos-uk", "routes");
});
await step("profile: an invalid phone number is rejected", async () => {
  await page.locator("#p-phone").fill("abc");
  await page.getByRole("button", { name: "Save details" }).click();
  await main.getByText(/isn't a valid phone number/).first().waitFor();
  await page.reload();
  await page.locator("#p-phone").waitFor();
});
await step("profile: marketing consent toggle records a timeline event", async () => {
  await page.getByLabel(/Agreed to receive WhatsApp offers/).click(); // updates after the server confirms
  await page.getByText("Marketing consent recorded by staff").waitFor();
  await until(async () => page.getByLabel(/Agreed to receive WhatsApp offers/).isChecked(), "checkbox ticked");
});
await step("profile: a note appears on the timeline and the box clears", async () => {
  await page.locator("#note").fill("Called, wants Friday flight");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByText("Called, wants Friday flight").waitFor();
  eq(await page.locator("#note").inputValue(), "", "note box should clear");
});
await step("profile: logging a quote sets status to Quoted", async () => {
  await page.getByRole("button", { name: "Log a quote" }).click();
  await page.locator("#quote-text").fill("China air 30kg door delivery");
  await page.getByRole("dialog").getByRole("button", { name: "Save quote" }).click();
  await page.getByText("Quote sent").first().waitFor();
  await until(async () => (await page.locator("#p-status").inputValue()) === "quoted", "status Quoted");
});
await step("profile: recording a shipment updates totals, route and status (Booked)", async () => {
  await page.getByRole("button", { name: "Record shipment" }).click();
  await page.locator("#ship-amount").fill("150000");
  await page.locator("#ship-route").selectOption("china-air");
  await page.getByRole("dialog").getByRole("button", { name: "Record shipment" }).click();
  await until(async () => (await page.locator("#p-status").inputValue()) === "booked", "status Booked");
  await page.locator(".facts").getByText(/₦150,000/).waitFor();
  await page.getByText(/Status: quoted → booked/).waitFor();
});
await step("profile: manual status change records a lost reason, and can be changed back", async () => {
  await page.locator("#p-status").selectOption("lost");
  await until(async () => (await page.locator("#p-status").inputValue()) === "lost", "status Lost");
  await page.getByText(/Lost because: Price too high/).waitFor();
  await page.locator("#p-status").selectOption("repeat");
  await until(async () => (await page.locator("#p-status").inputValue()) === "repeat", "status Repeat");
});
await step("profile: do-not-contact persists across reload and can be cleared", async () => {
  await page.getByLabel(/Do not contact/).click();
  await until(async () => page.getByLabel(/Do not contact/).isChecked(), "DNC ticked");
  await page.reload();
  await page.getByLabel(/Do not contact/).waitFor();
  ok(await page.getByLabel(/Do not contact/).isChecked(), "DNC should persist");
  await page.getByLabel(/Do not contact/).click();
  await until(async () => !(await page.getByLabel(/Do not contact/).isChecked()), "DNC cleared");
});
await step("profile: delete asks for confirmation, then removes the customer", async () => {
  await page.getByRole("button", { name: "Delete customer" }).click();
  await page.getByRole("dialog").getByText(/permanently removes/).waitFor();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await page.waitForURL(/\/customers$/);
  await waitCount(60);
});
await step("a missing profile shows a clear error", async () => {
  await page.goto(BASE + "/customers/999999");
  await page.getByText("Customer not found").waitFor();
});

// ============ SEGMENTS ============
await step("filtered view saves as a segment with a live count", async () => {
  await page.goto(BASE + "/customers");
  await waitCount(60);
  ok(await main.getByRole("button", { name: "Save as segment" }).isDisabled(), "Save as segment disabled with no filters");
  await page.getByRole("button", { name: /^Filters/ }).click();
  await chip("Booked").click();
  await waitCount(6);
  await main.getByRole("button", { name: "Save as segment" }).click();
  await page.locator("#segment-name").fill("Existing customers");
  await page.getByRole("dialog").getByRole("button", { name: "Save segment" }).click();
  await page.waitForURL(/\/segments$/);
  const row = page.locator("tbody tr", { hasText: "Existing customers" });
  await row.waitFor();
  ok((await row.innerText()).includes("6"), "segment count should be 6");
});
await step("a duplicate segment name is rejected; a new name saves", async () => {
  await page.goto(BASE + "/customers?f=" + encodeURIComponent(JSON.stringify({ statuses: ["dormant"] })));
  await waitCount(4);
  await main.getByRole("button", { name: "Save as segment" }).click();
  await page.locator("#segment-name").fill("Existing customers");
  await page.getByRole("dialog").getByRole("button", { name: "Save segment" }).click();
  await page.getByRole("dialog").getByText(/already exists/).waitFor();
  await page.locator("#segment-name").fill("Past customers");
  await page.getByRole("dialog").getByRole("button", { name: "Save segment" }).click();
  await page.waitForURL(/\/segments$/);
});
await step("segment 'View' reopens the filtered customers", async () => {
  await page.locator("tbody tr", { hasText: "Past customers" }).getByRole("link", { name: "View" }).click();
  await page.waitForURL(/\/customers\?f=/);
  await waitCount(4);
});

// ============ CAMPAIGN BUILDER (reactive) ============
await step("segment 'Message' opens the builder with the segment preselected and a live audience", async () => {
  await page.goto(BASE + "/segments");
  await page.locator("tbody tr", { hasText: "Existing customers" }).getByRole("link", { name: "Message" }).click();
  await page.waitForURL(/campaigns\/new\?segment=/);
  await until(async () => (await page.locator("#c-segment").inputValue()) !== "", "segment preselected");
  await until(async () => (await page.locator("aside .big").innerText()) === "6", "audience 6");
});
await step("audience, fees and exclusions update live as filters, channel and message type change", async () => {
  const big = () => page.locator("aside .big").innerText();
  const aside = () => page.locator("aside").innerText();
  await page.locator("#c-segment").selectOption("");
  await until(async () => (await big()) === "60", "audience 60 without segment");
  await chip("Booked").click();
  await until(async () => (await big()) === "6", "audience 6 with Booked filter");
  await until(async () => /₦504/.test(await aside()), "fee ₦504 for 6 marketing messages");
  await page.locator("#c-category").selectOption("utility");
  await until(async () => /₦84\b/.test(await aside()), "fee ₦84 for 6 utility messages");
  await page.locator("#c-channel").selectOption("email");
  await until(async () => (await big()) === "2", "email audience 2 (customers with an email)");
  await until(async () => /No email address/.test(await aside()), "email exclusion shown");
  await page.locator("#c-channel").selectOption("whatsapp");
  await page.locator("#c-category").selectOption("marketing");
  await until(async () => (await big()) === "6", "back to 6");
});
await step("message step: placeholders render in the preview; attachment chip appears", async () => {
  await page.locator("#c-name").fill("E2E win-back");
  await page.getByRole("tab", { name: /2\. Message/ }).click();
  await page.locator("#c-body").fill("Hi {first_name}, China air closes Friday. Free delivery to {city}!");
  await until(async () => /Hi Ada, China air closes Friday\. Free delivery to Ikeja!/.test(await page.locator(".bubble").innerText()), "preview with sample data");
  await page.locator("#c-media-type").selectOption("image");
  await until(async () => /Image/.test(await page.locator(".bubble .media").innerText()), "media chip");
  await page.locator("#c-media-type").selectOption("");
});
await step("sending with no message is refused with a clear message", async () => {
  await page.locator("#c-body").fill("");
  await page.getByRole("tab", { name: /3\. Send/ }).click();
  await page.getByRole("button", { name: /^Send to/ }).click();
  await page.getByText(/Write a message/).waitFor();
  await page.getByRole("tab", { name: /2\. Message/ }).click();
  await page.locator("#c-body").fill("Hi {first_name}, China air closes Friday. Free delivery to {city}!");
});
await step("send now: opens the campaign page, reaches Sent, lists every recipient", async () => {
  await page.getByRole("tab", { name: /3\. Send/ }).click();
  await page.getByText(/This sends to/).waitFor();
  await page.getByRole("button", { name: /^Send to 6$/ }).click();
  await page.waitForURL(/\/campaigns\/\d+$/);
  await page.getByRole("heading", { name: "E2E win-back" }).waitFor();
  await until(async () => (await page.locator(".pill.cs-sent").count()) > 0, "campaign to reach Sent", 15000);
  await until(async () => /SENT\s*6/i.test((await page.locator(".tiles").innerText()).replace(/\n/g, " ")), "tiles show 6 sent");
  await page.getByText(/test mode: nothing was really sent/).waitFor();
  eq(await page.locator("tbody tr").count(), 6, "recipient rows");
});
await step("recipient status filter works", async () => {
  await page.locator("#rec-filter").selectOption("failed");
  await until(async () => (await page.locator("tbody tr").count()) === 0, "no failed recipients");
  await main.getByText("No recipients in this view.").waitFor();
  await page.locator("#rec-filter").selectOption("");
  await until(async () => (await page.locator("tbody tr").count()) === 6, "all 6 again");
});
await step("the campaign shows on a recipient's timeline", async () => {
  await page.locator("tbody tr").first().getByRole("link").click();
  await page.getByText(/Campaign sent: E2E win-back/).waitFor();
});
await step("campaign list shows the campaign as Sent", async () => {
  await page.getByRole("link", { name: "Campaigns" }).first().click();
  const row = page.locator("tbody tr", { hasText: "E2E win-back" });
  await row.waitFor();
  ok(/Sent/.test(await row.innerText()), "row should say Sent");
});
await step("duplicate opens an editable draft named (copy)", async () => {
  await page.locator("tbody tr", { hasText: "E2E win-back" }).click();
  await page.getByRole("button", { name: "Duplicate" }).click();
  await page.waitForURL(/\/campaigns\/\d+\/edit$/);
  await until(async () => (await page.locator("#c-name").inputValue()) === "E2E win-back (copy)", "name prefilled");
});
await step("schedule for later, then cancel it", async () => {
  await page.getByRole("tab", { name: /3\. Send/ }).click();
  await page.getByLabel("Schedule for later").check();
  const d = new Date(Date.now() + 86400000);
  const pad = (n) => String(n).padStart(2, "0");
  await page.locator("#c-send-at").fill(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00`);
  await page.getByRole("button", { name: "Schedule campaign" }).click();
  await page.waitForURL(/\/campaigns\/\d+$/);
  await page.locator(".pill.cs-scheduled").waitFor();
  await page.getByRole("button", { name: "Cancel campaign" }).click();
  await page.locator(".pill.cs-cancelled").waitFor();
});
await step("a draft can be saved and reopened from the list", async () => {
  await page.goto(BASE + "/campaigns/new");
  await page.locator("#c-name").fill("Draft only");
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.waitForURL(/\/campaigns$/);
  await page.locator("tbody tr", { hasText: "Draft only" }).click();
  await page.waitForURL(/\/edit$/);
  await until(async () => (await page.locator("#c-name").inputValue()) === "Draft only", "saved draft name to load into the form");
});

// ============ DASHBOARD ============
await step("dashboard numbers reflect the data; status bars link to filtered lists", async () => {
  await page.getByRole("link", { name: "Dashboard" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  const tiles = (await page.locator(".tiles").innerText()).replace(/\n/g, " ");
  ok(/CUSTOMERS\s*60/.test(tiles), "60 customers: " + tiles);
  ok(/MESSAGES SENT \(30 DAYS\)\s*6/.test(tiles), "6 messages: " + tiles);
  await page.getByText(/4 dormant customers/).waitFor();
  await main.getByRole("link", { name: /Booked/ }).first().click();
  await page.waitForURL(/\/customers\?f=/);
  await waitCount(6);
});

// ============ SESSION ============
await step("sign out returns to login and protects the pages again", async () => {
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL(/\/login$/);
  await page.goto(BASE + "/campaigns");
  await until(async () => page.url().endsWith("/login"), "redirect after sign-out");
});
await step("an invalid or expired token is bounced to login", async () => {
  await page.evaluate(() => localStorage.setItem("kgl_token", "garbage"));
  await page.goto(BASE + "/customers");
  await until(async () => page.url().endsWith("/login"), "redirect on 401");
});

// ============ MOBILE ============
await step("phone layout (390px): no page-level sideways scroll on any screen", async () => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(BASE + "/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  const bad = [];
  for (const url of ["/", "/customers", "/segments", "/campaigns", "/campaigns/new"]) {
    await page.goto(BASE + url);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(400);
    const w = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
    if (w.sw > w.iw + 1) bad.push(`${url} (${w.sw}px > ${w.iw}px)`);
    await page.screenshot({ path: path.join(shots, "mobile-" + (url === "/" ? "dashboard" : url.slice(1).replace(/\//g, "-")) + ".png") });
  }
  ok(bad.length === 0, "horizontal overflow on: " + bad.join(", "));
});

await page.setViewportSize({ width: 1366, height: 800 });
for (const [url, name] of [["/customers", "desktop-customers"], ["/campaigns/new", "desktop-campaign"]]) {
  await page.goto(BASE + url);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(shots, name + ".png") });
}
await browser.close();

// ---- report ----
const failed = results.filter((r) => !r.ok);
const unexpected = badRequests.filter((b) => !/^(401|404|409|422) /.test(b));
console.log("\n==== SUMMARY ====");
console.log(`${results.length - failed.length}/${results.length} steps passed`);
console.log(`API 4xx responses seen: ${badRequests.length} (validation/auth refusals the steps provoke on purpose); unexpected (5xx or other): ${unexpected.length}`);
unexpected.forEach((u) => console.log("  " + u));
const realConsole = consoleErrors.filter((c) => !/Failed to load resource/.test(c));
console.log(`browser console/page errors (excluding expected failed-request lines): ${realConsole.length}`);
realConsole.slice(0, 10).forEach((c) => console.log("  " + c));
console.log("screenshots: " + shots);
if (failed.length) { console.log("\nFAILED STEPS:"); failed.forEach((f) => console.log(` - ${f.name}\n     ${f.err}`)); }
process.exit(failed.length || unexpected.length || realConsole.length ? 1 : 0);
