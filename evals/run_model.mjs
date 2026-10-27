// Run the seed questions through angka's three steps (via the Worker on wrangler dev) and score
// the results against the reference answers in evals/gold.json.
//
//   npx wrangler dev --port 8787            (in another terminal)
//   node evals/run_model.mjs [--model @cf/...] [--only 1,4,22] [--base http://localhost:8787]
//
// Every run spends the account's free Workers AI allowance (10,000 neurons, about US$0.11 a day),
// so the estimated cost of each run is printed and saved with the results.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { DuckDBInstance } from "@duckdb/node-api";
import * as E from "../public/engine.js";

const ROOT = new URL("..", import.meta.url).pathname;
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const model = arg("model", E.DEFAULT_MODEL);
const base = arg("base", "http://localhost:8787");
const only = arg("only", "") ? new Set(arg("only").split(",").map(Number)) : null;

// US$ per million tokens (input, output), from the Workers AI model list on 2026-10-27
const PRICES = {
  "@cf/google/gemma-4-26b-a4b-it": [0.1, 0.3],
  "@cf/qwen/qwen3-30b-a3b-fp8": [0.0509, 0.335],
  "@cf/zai-org/glm-4.7-flash": [0.0605, 0.4],
  "@cf/openai/gpt-oss-20b": [0.2, 0.3],
  "@cf/openai/gpt-oss-120b": [0.35, 0.75],
  "@cf/deepseek-ai/deepseek-v4.1-flash-1017": [0.3, 1.2],
  "@cf/meta/llama-4-scout-17b-16e-instruct": [0.27, 0.85],
  "@cf/mistralai/mistral-small-3.1-24b-instruct": [0.351, 0.555],
};
const DAILY_FREE_USD = 0.11;

const catalogue = JSON.parse(readFileSync(`${ROOT}public/data/catalogue.json`, "utf8"));
const gold = JSON.parse(readFileSync(`${ROOT}evals/gold.json`, "utf8"));

const db = await DuckDBInstance.create();
const con = await db.connect();
for (const t of catalogue.tables) {
  await con.run(`CREATE VIEW ${t.id} AS SELECT * FROM read_parquet('${ROOT}public/data/${t.id}.parquet')`);
}

async function step(path, body) {
  const res = await fetch(`${base}/api/${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...body, model }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`${path}: ${data.error} ${data.message || ""}`.trim());
  return data;
}

async function runSql(sql) {
  const reader = await con.runAndReadAll(sql);
  return { columns: reader.columnNames(), rows: E.plainRows(reader.getRowObjectsJS().slice(0, 200)) };
}

// The same flow as the browser page: pick -> sql (one retry on error) -> run -> answer
async function ask(question) {
  const trace = { usage: { input: 0, output: 0, neurons: 0 } };
  const add = (u) => {
    trace.usage.input += u?.input || 0;
    trace.usage.output += u?.output || 0;
    trace.usage.neurons += u?.neurons || 0;
  };
  const pick = await step("pick", { question });
  add(pick.usage);
  trace.tables = pick.tables;
  if (!pick.tables.length) {
    trace.refused = pick.refuse;
    return trace;
  }
  let previous = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const s = await step("sql", { question, tables: pick.tables, previous });
    add(s.usage);
    trace.sql = s.sql;
    trace.chart = s.chart;
    const problem = s.problem || E.checkSql(s.sql, pick.tables);
    if (problem) trace.advice = (trace.advice || []).concat(problem);
    if (problem) {
      previous = { sql: s.sql, error: problem };
      trace.error = problem;
      continue;
    }
    try {
      const r = await runSql(s.sql);
      trace.columns = r.columns;
      trace.rows = r.rows;
      trace.error = null;
      break;
    } catch (e) {
      previous = { sql: s.sql, error: String(e.message).split("\n")[0].slice(0, 400) };
      trace.error = previous.error;
    }
  }
  trace.retried = previous !== null;
  if (trace.rows) {
    const a = await step("answer", { question, tables: pick.tables, sql: trace.sql, columns: trace.columns, rows: E.sampleRows(trace.rows, 30) });
    add(a.usage);
    trace.answer = a.answer;
  }
  return trace;
}

// ---- scoring --------------------------------------------------------------------------------

const isDate = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v);
const near = (a, b) => {
  if (a === b) return true;
  const tol = Math.max(Math.abs(a) * 0.006, 0.051);
  // allow the same number in another unit (thousands, per cent)
  return [1, 1000, 0.001, 100, 0.01].some((k) => Math.abs(a * k - b) <= tol * Math.max(k, 1));
};

function rowMatches(goldRow, gotRow) {
  const nums = gotRow.filter((v) => typeof v === "number");
  const years = gotRow.filter(isDate).map((v) => Number(v.slice(0, 4)));
  const texts = gotRow.filter((v) => typeof v === "string").map((v) => v.toLowerCase());
  const numMatch = (v) => (Number.isInteger(v) && v >= 1900 && v <= 2100 && years.includes(v)) || nums.some((n) => near(v, n));
  const words = goldRow.filter((v) => typeof v === "string" && !isDate(v));
  const numbers = goldRow.filter((v) => typeof v === "number");
  // every name must match; of several numbers, one is enough for now (M3 brings stricter grading)
  return words.every((v) => texts.includes(v.toLowerCase())) && (!numbers.length || numbers.some(numMatch));
}

function score(g, t) {
  if (!t.refused && !t.rows && !t.sql && t.error) return `error: ${t.error}`;
  if (g.status === "gap" || g.status === "refuse") {
    return t.refused ? "pass" : "fail: answered a question it should have refused";
  }
  if (t.refused) return "fail: refused";
  if (!t.rows) return `fail: no result (${t.error})`;
  const gotRows = t.rows.map((r) => t.columns.map((c) => r[c]));
  let goldRows = g.rows.slice(0, 20);
  if (g.key) {
    const keep = g.key.map((k) => g.columns.indexOf(k));
    goldRows = goldRows.map((r) => keep.map((i) => r[i]));
  }
  const matched = goldRows.filter((gr) => gotRows.some((r) => rowMatches(gr, r))).length;
  const need = goldRows.length === 1 ? 1 : Math.ceil(goldRows.length * 0.8);
  return matched >= need ? "pass" : `fail: ${matched}/${goldRows.length} reference rows found`;
}

// ---- run -----------------------------------------------------------------------------------

const results = [];
let usage = { input: 0, output: 0, neurons: 0 };
for (const g of gold) {
  if (only && !only.has(g.id)) continue;
  const started = Date.now();
  let t;
  try {
    t = await ask(g.question);
  } catch (e) {
    t = { error: String(e.message), usage: { input: 0, output: 0, neurons: 0 } };
    if (/daily_limit/.test(t.error)) {
      console.log("Daily free allowance used up; stopping.");
      break;
    }
  }
  t.seconds = Math.round((Date.now() - started) / 100) / 10;
  t.verdict = score(g, t);
  usage.input += t.usage.input;
  usage.output += t.usage.output;
  usage.neurons += t.usage.neurons;
  results.push({ id: g.id, lang: g.lang, status: g.status, question: g.question, ...t });
  console.log(`Q${g.id} ${g.lang.padEnd(5)} ${t.verdict.startsWith("pass") ? "✓" : "✗"} ${t.verdict}${t.answer ? "\n      " + t.answer.replace(/\s+/g, " ").slice(0, 200) : t.refused ? "\n      [refused] " + t.refused.slice(0, 160) : ""}`);
}

const [pin, pout] = PRICES[model] || [0, 0];
// Workers AI reports the neurons each call used; fall back to the price list if it doesn't
const usd = usage.neurons ? (usage.neurons * 0.011) / 1000 : (usage.input * pin + usage.output * pout) / 1e6;
const passed = results.filter((r) => r.verdict === "pass").length;
const byStatus = {};
for (const r of results) {
  const k = r.status === "partial" ? "ok" : r.status === "gap" ? "refuse" : r.status;
  byStatus[k] = byStatus[k] || [0, 0];
  byStatus[k][1]++;
  if (r.verdict === "pass") byStatus[k][0]++;
}
const summary = {
  model,
  date: new Date().toISOString(),
  questions: results.length,
  passed,
  score: results.length ? Math.round((1000 * passed) / results.length) / 10 : 0,
  by_kind: Object.fromEntries(Object.entries(byStatus).map(([k, [p, n]]) => [k, `${p}/${n}`])),
  tokens: usage,
  neurons: Math.round(usage.neurons),
  est_usd: Math.round(usd * 10000) / 10000,
  share_of_daily_free: Math.round((100 * usd) / DAILY_FREE_USD) + "%",
};
console.log("\n" + JSON.stringify(summary, null, 1));

mkdirSync(`${ROOT}evals/results`, { recursive: true });
const name = `${summary.date.slice(0, 16).replace(/[:T]/g, "")}-${model.split("/").pop()}${only ? "-subset" : ""}.json`;
writeFileSync(`${ROOT}evals/results/${name}`, JSON.stringify({ summary, results }, null, 1));
console.log(`saved evals/results/${name}`);
