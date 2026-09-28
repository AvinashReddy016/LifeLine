/**
 * Drives the real frontend against the mock backend in headless Chrome.
 *
 * Checks, per answer case:
 *   - no raw markdown syntax (pipes, **, ##) inside the rendered answer
 *   - real <table> elements are rendered
 *   - zero-evidence case shows the "No historical records found" banner
 *   - conflict case shows the POTENTIAL CONFLICT badge
 *   - source records section state is correct
 *   - layout is clean at 1920x1080 (no horizontal page overflow)
 *
 * Usage:
 *   node visual_test/visual_test.mjs           (starts its own vite + mock backend, cleans up)
 *   node visual_test/visual_test.mjs --keep    (same, but leaves servers running)
 *   VITE_API_URL must point at the mock backend (the script sets it for its own vite).
 */
import { spawn, execSync, execFileSync } from "node:child_process";
import http from "node:http";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const FRONTEND_DIR = resolve(PROJECT_ROOT, "frontend");
const MOCK_PORT = 8001;
const VITE_PORT = 5199;
const W = 1920;
const H = 1080;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function waitFor(url, tries = 40, delay = 500) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http
        .get(url, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => {
          if (n <= 0) reject(new Error(`timeout waiting for ${url}`));
          else setTimeout(() => attempt(n - 1), delay);
        });
    };
    attempt(tries);
  });
}

let mockProc, viteProc;
async function startServers() {
  mockProc = spawn("python", [resolve(PROJECT_ROOT, "visual_test/mock_backend.py")], {
    cwd: PROJECT_ROOT,
    stdio: "ignore",
  });
  // Run vite directly via node to avoid cmd.exe (unavailable in this sandbox).
  viteProc = spawn(process.execPath, ["node_modules/vite/bin/vite.js", "--port", String(VITE_PORT), "--host", "127.0.0.1"], {
    cwd: FRONTEND_DIR,
    env: { ...process.env, VITE_API_URL: `http://127.0.0.1:${MOCK_PORT}` },
    stdio: "ignore",
  });
  await waitFor(`http://127.0.0.1:${MOCK_PORT}/api/patients`);
  await waitFor(`http://127.0.0.1:${VITE_PORT}`);
  console.log("servers ready");
}

function stopServers() {
  for (const p of [viteProc, mockProc]) {
    try {
      p && p.pid && execFileSync("taskkill", ["/pid", String(p.pid), "/t", "/f"], { stdio: "ignore" });
    } catch { /* already gone */ }
  }
}

async function newPage(driver) {
  const res = await fetch(`http://127.0.0.1:9222/json/new?about:blank`, { method: "PUT" });
  const target = await res.json();
  const page = await driver.attach(target.webSocketDebuggerUrl);
  await page.send("Emulation.setDeviceMetricsOverride", {
    width: W, height: H, deviceScaleFactor: 1, mobile: false,
  });
  return page;
}

async function evalValue(page, expression) {
  const { result, exceptionDetails } = await page.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
  });
  if (exceptionDetails) {
    throw new Error(`evaluate failed: ${exceptionDetails.text} ${JSON.stringify(exceptionDetails.exception?.description ?? "")}`);
  }
  return result.value;
}

const consoleErrors = [];

async function askAndSettle(page, question) {
  await page.send("Page.navigate", {
    url: `http://127.0.0.1:${VITE_PORT}/?view=patient&tab=ask`,
  });
  // Wait for the React app to actually mount the ask form.
  let mounted = false;
  for (let i = 0; i < 60; i++) {
    try {
      if ((await evalValue(page, `document.getElementById('ask-input') ? 'yes' : 'no'`)) === "yes") {
        mounted = true;
        break;
      }
    } catch { /* page still navigating */ }
    await sleep(500);
  }
  if (!mounted) {
    const body = await evalValue(page, `document.body.innerText.slice(0, 500)`);
    throw new Error(`app never mounted. body: ${body}`);
  }
  await evalValue(page, `(() => {
    const input = document.getElementById('ask-input');
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(question)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return 'ok';
  })()`);
  await evalValue(page, `document.querySelector('.ask-btn').click(); 'clicked'`);
  // Wait for the answer stack to appear and settle.
  for (let i = 0; i < 40; i++) {
    if ((await evalValue(page, `document.querySelector('.answer-stack') ? 'yes' : 'no'`)) === "yes") break;
    await sleep(250);
    if (i === 39) {
      const body = await evalValue(page, `document.body.innerText.slice(0, 800)`);
      throw new Error(`answer never rendered. body: ${body}`);
    }
  }
  await sleep(1200);
}

const exprs = {
  rawMarkdown: `(() => {
    const stack = document.querySelector('.answer-stack');
    if (!stack) return 'no stack';
    const t = stack.innerText;
    const bad = [];
    if (/\\|\\s*-{3,}/.test(t)) bad.push('table-separator');
    if (/\\|\\s*What changed/.test(t) && !stack.querySelector('table')) bad.push('pipe-row');
    if (/\\*\\*/.test(t)) bad.push('bold');
    if (/^#{1,6}\\s/m.test(t)) bad.push('heading');
    return bad.join(', ') || 'clean';
  })()`,
  tables: `document.querySelectorAll('.answer-stack table.md-table').length`,
  banner: `document.querySelector('.no-records-banner') ? document.querySelector('.no-records-title').innerText : 'none'`,
  badge: `document.querySelector('.conflict-badge') ? document.querySelector('.conflict-badge').innerText : 'none'`,
  sources: `(() => {
    const chips = document.querySelectorAll('.source-record');
    if (chips.length) return chips.length + ' chips: ' + [...chips].map(c => c.querySelector('.source-record-rid').innerText).join(', ');
    const empty = [...document.querySelectorAll('.source-records .empty-note')].map(e => e.innerText).join(' | ');
    return empty || 'no section';
  })()`,
  evidence: `(() => {
    const head = document.querySelector('.memory-evidence-head .memory-evidence-count');
    return head ? head.innerText : 'no section';
  })()`,
  findings: `(() => {
    const f = document.querySelector('.answer-findings .answer-subheading');
    return f ? f.innerText : 'none';
  })()`,
  overflow: `(() => {
    const de = document.documentElement;
    return (de.scrollWidth > de.clientWidth + 1) ? 'OVERFLOWS' : 'ok';
  })()`,
  tableScrollable: `(() => {
    const wrap = document.querySelector('.md-table-scroll');
    if (!wrap) return 'no table';
    return wrap.scrollWidth > wrap.clientWidth ? 'scrolls' : 'fits';
  })()`,
  ridChips: `document.querySelectorAll('.answer-stack .md-rid').length`,
  unresolved: `(() => {
    const items = document.querySelectorAll('.verification-item .verification-status');
    return items.length ? [...items].map(i => i.innerText).join(' | ') : 'none';
  })()`,
};

async function evaluateAll(page) {
  const out = {};
  for (const [name, expression] of Object.entries(exprs)) {
    const { result } = await page.send("Runtime.evaluate", { expression, returnByValue: true });
    out[name] = result.value;
  }
  return out;
}

async function shot(page, name) {
  const { data } = await page.send("Page.captureScreenshot", { format: "png" });
  const { writeFileSync } = await import("node:fs");
  writeFileSync(resolve(PROJECT_ROOT, `visual_test/${name}.png`), Buffer.from(data, "base64"));
}

const CASES = [
  { name: "case2-changes", question: "What changed since the last hospital visit?" },
  { name: "case3-conflict", question: "Are there conflicting entries in the patient's history?" },
  { name: "case4-no-records", question: "What did the patient eat for breakfast in 2019?" },
];

let failed = false;

const driver = await import("chrome-remote-interface").catch(() => null);
if (!driver) {
  console.error("chrome-remote-interface not installed; run: npm i -g chrome-remote-interface");
  process.exit(1);
}

try {
  await startServers();

  // Launch headless Chrome with remote debugging.
  const chromePaths = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    process.env.LOCALAPPDATA + "/Google/Chrome/Application/chrome.exe",
  ];
  const fs = await import("node:fs");
  const chrome = chromePaths.find((p) => fs.existsSync(p));
  if (!chrome) throw new Error("Chrome not found");
  const chromeProc = spawn(chrome, [
    "--headless=new",
    `--remote-debugging-port=9222`,
    `--user-data-dir=${process.env.TEMP}/lifeline-visual-test`,
    "--no-first-run", "--no-default-browser-check", "--window-size=1920,1080",
    "about:blank",
  ], { stdio: "ignore" });
  await waitFor("http://127.0.0.1:9222/json/version");

  const CDP = driver.default;
  const cdp = await CDP({ port: 9222 });
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  cdp.on("Runtime.consoleAPICalled", (e) => {
    if (e.type === "error" || e.type === "warning") {
      consoleErrors.push(e.args.map((a) => a.value ?? a.description ?? "").join(" "));
    }
  });
  cdp.on("Runtime.exceptionThrown", (e) => {
    consoleErrors.push(e.exceptionDetails?.exception?.description ?? "exception");
  });
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: W, height: H, deviceScaleFactor: 1, mobile: false,
  });

  for (const c of CASES) {
    console.log(`\n=== ${c.name}: "${c.question}" ===`);
    await askAndSettle(cdp, c.question);
    const r = await evaluateAll(cdp);
    for (const [k, v] of Object.entries(r)) console.log(`  ${k}: ${v}`);
    if (consoleErrors.length) console.log(`  console errors: ${consoleErrors.splice(0).join(" | ").slice(0, 400)}`);

    if (c.name === "case2-changes") {
      if (!/clean/.test(r.rawMarkdown)) fail("raw markdown visible");
      if (r.tables < 1) fail("no table rendered");
      if (!/chips/i.test(r.sources)) fail("source records missing");
      if (!/memor/i.test(r.evidence)) fail("evidence missing");
      if (!/key findings/i.test(r.findings)) fail("findings label wrong");
      if (r.overflow !== "ok") fail("page overflows at 1920x1080");
      if (r.ridChips < 1) fail("record id chips missing in answer");
    }
    if (c.name === "case3-conflict") {
      if (!/POTENTIAL CONFLICT/i.test(r.badge)) fail("conflict badge missing");
      if (!/UNRESOLVED/.test(r.unresolved)) fail("conflict not marked unresolved");
      if (r.tables < 1) fail("no conflict table rendered");
      if (!/clean/.test(r.rawMarkdown)) fail("raw markdown visible");
    }
    if (c.name === "case4-no-records") {
      if (!/No historical records found/i.test(r.banner)) fail("no-records banner missing");
      if (!/no source records/i.test(r.sources)) fail("source section should say none");
      if (!/no historical evidence/i.test(r.evidence)) fail("evidence section should say none");
      if (!/Items to verify/i.test(r.findings)) fail("findings should be labeled Items to verify");
      if (r.overflow !== "ok") fail("page overflows at 1920x1080");
    }
    await shot(cdp, c.name);
  }

  if (!failed) console.log("\nALL VISUAL CHECKS PASSED");
} catch (e) {
  failed = true;
  console.error("VISUAL TEST FAILED:", e.message);
} finally {
  try { cdp && cdp.close(); } catch { /* ignore */ }
  stopServers();
  if (!process.argv.includes("--keep")) {
    try { execFileSync("taskkill", ["/im", "chrome.exe", "/f"], { stdio: "ignore" }); } catch { /* not running */ }
  }
  process.exit(failed ? 1 : 0);
}

function fail(msg) {
  failed = true;
  console.error(`  ✗ FAIL: ${msg}`);
}
