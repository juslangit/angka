// Check the wording of each answer in a results file with the `claude` CLI (Luqman's
// subscription, no API key), then write the verdicts back into the file.
//
//   node evals/judge.mjs evals/results/<file>.json
//
// The number check in run_model.mjs asks "did the query get the right data?". This asks
// "did the sentence the visitor reads say it properly?":
//   language  — same language as the question (rojak may be answered in rojak, BM or a mix)
//   faithful  — every number in the answer is in the result, allowing rounding and units
//   period    — it says which date or period the numbers are for (not needed for refusals)
//   caveat    — where the reference note names a caveat, the answer mentions it
// For a test-set file only the totals are printed.

import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { sampleRows } from "../public/engine.js";

const file = process.argv[2];
if (!file) {
  console.error("usage: node evals/judge.mjs evals/results/<file>.json");
  process.exit(1);
}
const run = JSON.parse(readFileSync(file, "utf8"));
const BATCH = 20;

const SCHEMA = {
  type: "object",
  properties: {
    verdicts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "integer" },
          language: { type: "boolean" },
          faithful: { type: "boolean" },
          period: { type: "boolean" },
          caveat: { type: "boolean" },
          why: { type: "string", description: "one short sentence, only when something is false" },
        },
        required: ["id", "language", "faithful", "period", "caveat", "why"],
        additionalProperties: false,
      },
    },
  },
  required: ["verdicts"],
  additionalProperties: false,
};

const SYSTEM = `You grade answers written by a Malaysian statistics assistant. For each item you get the question,
its language (EN, BM or rojak), the query result the answer had to use, the answer, and sometimes a reference note.

Judge each item strictly but fairly:
- language: true if the answer is in the question's language. EN needs English. BM needs Malay. rojak may be answered in rojak, Malay, or a natural mix; plain English for a rojak question is false.
- faithful: true if every number in the answer appears in the result or follows from it by rounding, unit conversion (e.g. 4224300 = 4.22 juta = 4.2 million), or simple arithmetic on result values. Any number not supported by the result makes it false. For a refusal (no result), true unless it invents statistics.
- period: true if the answer says which date, month, year or period the numbers are for. For a refusal, true.
- caveat: if the reference note says the answer must state a caveat ("must say", "should say", "answer should"), true only if it does. Otherwise true.
- why: one short sentence naming what is wrong; empty string when all four are true.
Return one verdict per item, using its id.`;

function itemsFor(results) {
  return results
    .filter((r) => r.answer || r.refused)
    .map((r) => ({
      id: r.id,
      question: r.question,
      language: r.lang,
      note: r.note || "",
      result: r.rows ? { columns: r.columns, rows: sampleRows(r.rows, 30) } : "(no query: the assistant declined)",
      answer: r.answer || r.refused,
    }));
}

function judge(batch) {
  const prompt = `Grade these ${batch.length} items:\n\n${JSON.stringify(batch, null, 1)}`;
  const out = spawnSync(
    "claude",
    ["-p", prompt, "--restricted", "--no-session-persistence", "--model", "haiku", "--output-format", "json",
      "--system-prompt", SYSTEM, "--json-schema", JSON.stringify(SCHEMA)],
    { encoding: "utf8", maxBuffer: 20 * 1024 * 1024, timeout: 300000 },
  );
  if (out.status !== 0) throw new Error(`claude failed: ${out.stderr || out.stdout}`.slice(0, 500));
  const data = JSON.parse(out.stdout);
  if (data.is_error || !data.structured_output) throw new Error(`claude returned no verdicts: ${String(data.result).slice(0, 300)}`);
  return data.structured_output.verdicts;
}

const items = itemsFor(run.results);
const verdicts = new Map();
for (let i = 0; i < items.length; i += BATCH) {
  let batch = items.slice(i, i + BATCH);
  // A reply now and then comes back empty or short: ask again for what is missing, in groups
  // of 5 after the first retry.
  for (let attempt = 0; attempt < 4 && batch.length; attempt++) {
    const size = attempt < 2 ? batch.length : 5;
    for (let j = 0; j < batch.length; j += size) {
      const part = batch.slice(j, j + size);
      const wanted = new Set(part.map((b) => b.id));
      const got = judge(part);
      if (process.env.JUDGE_DEBUG) console.error(`attempt ${attempt}: asked ${[...wanted].join(",")} got ${got.map((v) => JSON.stringify(v.id)).join(",")}`);
      for (const v of got) if (wanted.has(v.id)) verdicts.set(v.id, v);
    }
    batch = batch.filter((b) => !verdicts.has(b.id));
  }
  process.stdout.write(`judged ${verdicts.size}/${items.length}\r`);
}
console.log();
const missing = items.filter((it) => !verdicts.has(it.id)).map((it) => it.id);
if (missing.length) console.log(`no verdict after retries: ${missing.join(", ")}`);

const isTest = run.summary.split === "test";
let answerOk = 0, both = 0;
const fails = { language: 0, faithful: 0, period: 0, caveat: 0 };
for (const r of run.results) {
  const v = verdicts.get(r.id);
  r.judge = v || null;
  r.answer_ok = !!v && v.language && v.faithful && v.period && v.caveat;
  for (const k of Object.keys(fails)) if (v && !v[k]) fails[k]++;
  if (r.answer_ok) answerOk++;
  if (r.answer_ok && r.verdict === "pass") both++;
  if (!isTest && v && !r.answer_ok) console.log(`Q${r.id} ${r.lang}: ${v.why}`);
}
const n = run.results.length;
run.summary.answers_ok = `${answerOk}/${n}`;
run.summary.answer_failures = fails;
run.summary.fully_correct = `${both}/${n}`;
run.summary.fully_correct_pct = Math.round((1000 * both) / n) / 10;
writeFileSync(file, JSON.stringify(run, null, 1));
console.log(JSON.stringify({ data_correct: `${run.summary.passed}/${n}`, answers_ok: run.summary.answers_ok, answer_failures: fails, fully_correct: run.summary.fully_correct, pct: run.summary.fully_correct_pct }, null, 1));
