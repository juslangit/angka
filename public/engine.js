// angka's engine: the prompts, the parsing of model replies, and the SQL safety check.
// Pure functions with no I/O, shared by the Worker (src/worker.js), the browser page
// (public/index.html) and the eval runner (evals/run_model.mjs), so all three behave the same.

export const DEFAULT_MODEL = "@cf/google/gemma-4-26b-a4b-it";

// Common names people type -> the value used in the data
const PLACE_NAMES =
  "KL / Kuala Lumpur = 'W.P. Kuala Lumpur'; Putrajaya = 'W.P. Putrajaya'; Labuan = 'W.P. Labuan'; " +
  "Penang / Pinang = 'Pulau Pinang'; Malacca = 'Melaka'; N9 / Negri = 'Negeri Sembilan'; " +
  "the country as a whole is 'Malaysia' where a state column has it, otherwise use the national table.";

const shortDesc = (s, n = 160) => {
  const t = (s || "").replace(/^\[[^\]]*\]\s*/, "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
};

const dateRange = (t) => {
  const d = t.columns.find((c) => c.name === "date");
  return d && d.min ? `${d.min.slice(0, 4)}–${d.max.slice(0, 7)}` : "";
};

// Step 1 prompt material: one line per table, a few thousand tokens for all 31.
export function tableIndex(catalogue) {
  return catalogue.tables
    .map((t) => {
      const cols = t.columns
        .map((c) => (c.type === "VARCHAR" || c.name === "date" ? c.name : `${c.name} (${c.title_en || c.name})`))
        .join(", ");
      const use = (t.why || "").replace(/\s*\(Q[^)]*\)/g, "");
      return `- ${t.id}: ${t.title_en}. ${(t.frequency || "").toLowerCase()}, ${dateRange(t)}. Use for: ${use}. Columns: ${cols}`;
    })
    .join("\n");
}

// Step 2 prompt material: full column documentation for the chosen tables only.
export function tableDetail(catalogue, ids) {
  return ids
    .map((id) => catalogue.tables.find((t) => t.id === id))
    .filter(Boolean)
    .map((t) => {
      const cols = t.columns.map((c) => {
        let line = `  - ${c.name} ${c.type}: ${shortDesc(c.description_en, 480)}`;
        if (c.min) line += ` Range ${c.min} to ${c.max}.`;
        if (c.values) {
          const vals = c.values.map((v) => (typeof v === "string" ? `'${v}'` : v.en ? `'${v.value}'=${v.en}` : `'${v.value}'`));
          line += ` Values: ${vals.join(", ")}.`;
        } else if (c.distinct_values) {
          line += ` (${c.distinct_values} distinct values)`;
        }
        return line;
      });
      const sample = t.sample.slice(0, 2).map((r) => JSON.stringify(r)).join("\n  ");
      const caveat = t.caveat_en ? `\nCaveat: ${shortDesc(t.caveat_en, 300)}` : "";
      return `TABLE ${t.id} — ${t.title_en}. ${shortDesc(t.description_en, 300)} Frequency: ${(t.frequency || "").toLowerCase()}.${caveat}\nColumns:\n${cols.join("\n")}\nSample rows:\n  ${sample}`;
    })
    .join("\n\n");
}

export function pickMessages(catalogue, question) {
  const system = `You route questions about Malaysia's official statistics to data tables.

Tables:
${tableIndex(catalogue)}

Reply with JSON only, no other text.
If the tables can answer the question: {"tables": ["<id>", ...]} with the 1 to 3 table ids needed.
If they cannot (forecasts or future values, opinions, personal advice, other countries, a topic none of the tables cover, or a breakdown the tables do not have, such as trade with a particular country or exports by state): {"tables": [], "refuse": "<one or two short sentences in the same language as the question: say plainly this data is not available here, and name the closest data that is>"}.
The question may be in English, Malay, or Malaysian rojak (a mix of both).`;
  return [
    { role: "system", content: system },
    { role: "user", content: question },
  ];
}

export function sqlMessages(catalogue, question, ids, today, previous) {
  const notes = catalogue.notes.map((n) => `- ${n}`).join("\n");
  const system = `You write one DuckDB SQL query that answers a question about Malaysia's official statistics.
Today is ${today}.

${tableDetail(catalogue, ids)}

Notes about all tables:
${notes}

Rules:
- Most tables hold many years. Always filter the date: if the question names no period, use the latest date in the table, date = (SELECT max(date) FROM <table>) (for monthly data summed into years, the latest full calendar year).
- Use only the tables above, by their id as the table name. One SELECT (WITH is fine). No other statements.
- Each table mixes total rows ('overall', 'both') with breakdown rows. Filter every breakdown column to exactly one value (usually the total) unless the question asks to break it down.
- Use the exact category values listed. Place names: ${PLACE_NAMES}
- "Now", "latest", "current", "sekarang", "terkini", "this week", "last month" mean the latest date in the table: date = (SELECT max(date) FROM <table>) with the same filters.
- "Last year" / "tahun lepas" means the calendar year before today's year; "this year" / "tahun ini" means today's year.
- Always return the date (or year) the numbers are for, and give columns clear names.
- Counts stored in thousands: multiply by 1000 when you show the count itself. Never multiply inside a ratio, share or growth rate. Keep RM and percentages as they are.
- "Which state/district has the most/least": ORDER BY and LIMIT 1. A comparison of two or more things ("X or Y", "compare", "ke", "atau", "berbanding"): one row for each thing, never LIMIT 1. A map: one row per state (or district) with the state column.
- Values that are not real places (such as 'Rakan Niaga' or 'Supra') never count as a state.
- A trend: one row per period, ordered by date. Growth between two dates: compute it in SQL.
- Return at most 200 rows.

Reply with JSON only: {"sql": "<the query>", "chart": "<number | bar | line | map | table>"}`;
  const messages = [
    { role: "system", content: system },
    { role: "user", content: question },
  ];
  if (previous) {
    messages.push({ role: "assistant", content: JSON.stringify({ sql: previous.sql }) });
    messages.push({ role: "user", content: `That query failed: ${previous.error}\nFix it and reply with JSON only.` });
  }
  return messages;
}

export function answerMessages(catalogue, question, ids, result) {
  const caveats = ids
    .map((id) => catalogue.tables.find((t) => t.id === id))
    .filter(Boolean)
    .map((t) => `${t.id}: ${t.title_en}${t.caveat_en ? ` (caveat: ${shortDesc(t.caveat_en, 200)})` : ""}`)
    .join("\n");
  const rows = JSON.stringify(sampleRows(result.rows, 30));
  const system = `You answer a question about Malaysia's official statistics from a database query result.

Write 1 to 3 short sentences:
- In the same language and tone as the question: English, Malay, or Malaysian rojak (a mix of both).
- Use only the numbers in the result. Round sensibly; write RM amounts, percentages and large numbers the way a Malaysian reader expects.
- Say which date or period the numbers are for.
- If the result is empty, say no matching data was found.
- If a table note below matters for this answer, mention it briefly.
- Plain text only, no lists, no markdown.

Tables used:
${caveats}`;
  return [
    { role: "system", content: system },
    {
      role: "user",
      content: `Question: ${question}\n\nSQL: ${result.sql}\n\nColumns: ${result.columns.join(", ")}\nRows${result.rows.length > 30 ? ` (${result.rows.length} in all; shown: the first, an even spread, and the last)` : ""}: ${rows}`,
    },
  ];
}

// Long results (trends) keep their start, an even spread, and the latest rows, so the answer
// step sees the whole period rather than only its beginning.
export function sampleRows(rows, max) {
  if (rows.length <= max) return rows;
  const head = 3, tail = 10, middle = max - head - tail;
  const step = (rows.length - head - tail) / middle;
  const mid = Array.from({ length: middle }, (_, i) => rows[head + Math.floor(i * step)]);
  return [...rows.slice(0, head), ...mid, ...rows.slice(-tail)];
}

// Models differ in reply shape and some think aloud first; keep only the final text.
export function replyText(out) {
  let text = "";
  if (typeof out === "string") text = out;
  else if (out?.response != null) text = typeof out.response === "string" ? out.response : JSON.stringify(out.response);
  else if (out?.choices?.[0]?.message) text = out.choices[0].message.content || "";
  else if (out?.result) return replyText(out.result);
  return text.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
}

export function usageOf(out) {
  const u = out?.usage || out?.result?.usage || {};
  return { input: u.prompt_tokens || 0, output: u.completion_tokens || 0, neurons: u.neurons || 0 };
}

// Extra request fields per model. Thinking is off: on the free allowance it costs output
// tokens, and with a short max_tokens it can use them all up before the reply starts.
export function modelOptions(model, wantJson) {
  const opts = {};
  if (/gemma-4|glm-4\.7/.test(model)) opts.chat_template_kwargs = { enable_thinking: false };
  if (wantJson && /gemma-4|glm-4\.7|qwen3|llama-3\.3|llama-4/.test(model)) opts.response_format = { type: "json_object" };
  return opts;
}

function firstJson(text) {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) throw new Error("no JSON in the model's reply");
  return JSON.parse(text.slice(start, end + 1));
}

export function parsePick(text, catalogue) {
  const j = firstJson(text);
  const known = new Set(catalogue.tables.map((t) => t.id));
  const tables = (Array.isArray(j.tables) ? j.tables : []).filter((id) => known.has(id)).slice(0, 3);
  if (!tables.length) return { tables: [], refuse: typeof j.refuse === "string" && j.refuse ? j.refuse : "This question can't be answered from the data here." };
  return { tables };
}

export function parseSql(text) {
  const j = firstJson(text);
  if (typeof j.sql !== "string" || !j.sql.trim()) throw new Error("the model's reply has no SQL");
  const charts = ["number", "bar", "line", "map", "table"];
  return { sql: j.sql.trim().replace(/;\s*$/, ""), chart: charts.includes(j.chart) ? j.chart : "table" };
}

// The query runs in the visitor's own browser over public files, but it still has to be
// one read-only SELECT over our tables: no file or network access, no settings.
const FORBIDDEN = /\b(read_\w+|copy|attach|detach|install|load|pragma|set|reset|create|insert|update|delete|drop|alter|export|import|call|checkpoint|vacuum|glob|getenv|query_table|query)\b/i;

export function checkSql(sql, allowedIds) {
  const s = sql
    .replace(/'(?:[^']|'')*'/g, "''") // ignore text inside string literals
    .replace(/\b(extract|trim|substring)\s*\(([^()]*?)\bfrom\b/gi, "$1($2 of"); // FROM inside these is not a table
  if (!/^\s*(select|with)\b/i.test(s)) return "The query must start with SELECT or WITH.";
  if (s.includes(";")) return "Only one statement is allowed.";
  const bad = s.match(FORBIDDEN);
  if (bad) return `'${bad[1]}' is not allowed.`;
  if (/\b(from|join)\s*''/i.test(s)) return "Read from the tables by name, not from a file path.";
  const known = new Set(allowedIds);
  for (const [, name] of s.matchAll(/\b(?:from|join)\s+([a-z_][a-z0-9_]*)/gi)) {
    const n = name.toLowerCase();
    if (!known.has(n) && !/^(select|lateral|unnest|range|generate_series)$/.test(n) && !cteNames(s).has(n)) {
      return `Unknown table '${name}'. Use only: ${allowedIds.join(", ")}.`;
    }
  }
  return null;
}

// A softer check, worth one retry: tables that hold many dates but a query that never
// mentions the date mixes years (e.g. the highest Gini of any year since 1974).
export function adviseSql(sql, ids, catalogue) {
  const dated = ids.filter((id) => catalogue.tables.find((t) => t.id === id)?.columns.some((c) => c.name === "date"));
  const s = sql.replace(/'(?:[^']|'')*'/g, "''");
  const from = s.search(/\bfrom\b/i);
  const afterFrom = from >= 0 ? s.slice(from) : s; // selecting the date is not filtering on it
  if (dated.length && !/\bdate\b|\byear\s*\(|\bdate_reg\b/i.test(afterFrom)) {
    return "The query does not filter by date, so it mixes every year in the table. Filter to the period the question asks about; if it names none, use the latest date.";
  }
  return null;
}

function cteNames(s) {
  return new Set([...s.matchAll(/\b([a-z_][a-z0-9_]*)\s+as\s*\(/gi)].map((m) => m[1].toLowerCase()));
}

// Values from DuckDB can be BigInt or Date; make rows JSON-safe for the answer step.
export function plainRows(rows) {
  return rows.map((r) =>
    Object.fromEntries(
      Object.entries(r).map(([k, v]) => [
        k,
        typeof v === "bigint" ? Number(v) : v instanceof Date ? v.toISOString().slice(0, 10) : v && typeof v === "object" && "toString" in v && !Array.isArray(v) ? String(v) : v,
      ]),
    ),
  );
}
