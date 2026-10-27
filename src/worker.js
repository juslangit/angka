// angka's Worker: serves the site from public/ and the three model steps under /api/.
// The SQL itself runs in the visitor's browser; the Worker only talks to Workers AI, so the
// prompts stay here and the endpoint can't be used as a general-purpose free chatbot.

import catalogue from "../public/data/catalogue.json";
import * as E from "../public/engine.js";

const MAX_QUESTION = 300;
const MAX_ROWS_JSON = 12000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    if (request.method !== "POST") return json({ error: "Use POST." }, 405);

    // local eval runs (ALLOW_MODEL_OVERRIDE) skip the per-visitor limit
    if (env.LIMITER && env.ALLOW_MODEL_OVERRIDE !== "1") {
      const ip = request.headers.get("cf-connecting-ip") || "local";
      const { success } = await env.LIMITER.limit({ key: ip });
      if (!success) return json({ error: "busy", message: "Too many questions at once. Wait a minute and try again." }, 429);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Send JSON." }, 400);
    }
    const question = String(body.question || "").trim().slice(0, MAX_QUESTION);
    if (!question) return json({ error: "Ask a question." }, 400);

    // Only local development may try other models (set ALLOW_MODEL_OVERRIDE in .dev.vars)
    const model = env.ALLOW_MODEL_OVERRIDE === "1" && body.model ? body.model : env.MODEL || E.DEFAULT_MODEL;

    try {
      if (url.pathname === "/api/pick") {
        const out = await run(env, model, E.pickMessages(catalogue, question), 300, true);
        return json({ ...E.parsePick(E.replyText(out), catalogue), usage: E.usageOf(out), model });
      }

      if (url.pathname === "/api/sql") {
        const ids = tablesFrom(body.tables);
        if (!ids.length) return json({ error: "No tables chosen." }, 400);
        const previous = body.previous && { sql: String(body.previous.sql || "").slice(0, 4000), error: String(body.previous.error || "").slice(0, 500) };
        const today = new Date().toISOString().slice(0, 10);
        const out = await run(env, model, E.sqlMessages(catalogue, question, ids, today, previous), 900, true);
        const parsed = E.parseSql(E.replyText(out));
        // advice only on the first attempt: if the model keeps its query, it runs as written
        const problem = E.checkSql(parsed.sql, ids) || (previous ? null : E.adviseSql(parsed.sql, ids, catalogue));
        return json({ ...parsed, problem, usage: E.usageOf(out), model });
      }

      if (url.pathname === "/api/answer") {
        const ids = tablesFrom(body.tables);
        const rows = Array.isArray(body.rows) ? E.sampleRows(body.rows.slice(0, 200), 30) : [];
        const result = { sql: String(body.sql || "").slice(0, 4000), columns: (body.columns || []).map(String).slice(0, 30), rows };
        if (JSON.stringify(result.rows).length > MAX_ROWS_JSON) result.rows = rows.slice(0, 10);
        const out = await run(env, model, E.answerMessages(catalogue, question, ids, result), 400);
        return json({ answer: E.replyText(out), usage: E.usageOf(out), model });
      }

      return json({ error: "Unknown endpoint." }, 404);
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      // Workers AI answers with an error once the free daily allowance is used up
      if (/neuron|quota|limit|4006|capacity/i.test(msg)) {
        return json({ error: "daily_limit", message: "angka has used up today's free AI allowance. Try again tomorrow." }, 503);
      }
      return json({ error: "model_error", message: msg.slice(0, 300) }, 502);
    }
  },
};

function tablesFrom(list) {
  const known = new Set(catalogue.tables.map((t) => t.id));
  return (Array.isArray(list) ? list : []).map(String).filter((id) => known.has(id)).slice(0, 3);
}

async function run(env, model, messages, maxTokens, wantJson = false) {
  const out = await env.AI.run(model, { messages, max_tokens: maxTokens, temperature: 0, ...E.modelOptions(model, wantJson) });
  if (env.ALLOW_MODEL_OVERRIDE === "1") console.log("RAW", model, JSON.stringify(out).slice(0, 3000));
  return out;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
