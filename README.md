# angka

Ask a question about Malaysia in BM, English or rojak and get an answer computed from official
open data, with the dataset it came from and the SQL that produced it.

> Work in progress. M1 (data) and M2 (engine) are done; evals, the real interface and launch come next.

## How it works

1. **Pick** — Gemma 4 26B on Cloudflare Workers AI reads a one-line summary of every table and
   picks the 1–3 it needs, or refuses (forecasts, opinions, other countries, data we don't have).
2. **SQL** — given the full column documentation of just those tables, it writes one DuckDB query.
   `public/engine.js` checks it is a single read-only SELECT over known tables, and asks for one
   retry if it never filters by date (a common way to mix up years).
3. **Run** — the query runs in your browser with DuckDB-WASM over small Parquet files.
4. **Answer** — the model writes 1–3 sentences in the language you asked in, using only the numbers
   in the result; the page shows the sources, the result table and the SQL.

The model never states a number itself: every number is computed by DuckDB from the data.
It all runs on Cloudflare's free plan (10,000 neurons a day); a question costs about 40 neurons.

```sh
npm install
npx wrangler dev                 # site + API on http://localhost:8787 (AI calls use the free allowance)
node evals/run_model.mjs         # run the 50 seed questions through the engine and score them
```

## Data

31 tables from [data.gov.my](https://data.gov.my) and [OpenDOSM](https://open.dosm.gov.my)
(population, births and deaths, household income, spending, poverty and inequality, prices and
inflation, jobs and wages, GDP, trade, exchange rates, fuel prices, vehicle registrations),
1.5 MB of Parquet in total.

```sh
uv run python etl/build.py       # download, tidy, write public/data/*.parquet + catalogue.json
uv run python evals/run_gold.py  # run the reference queries, write evals/coverage.md
```

- Tables are kept as published, so every value can be traced back to data.gov.my. The only
  changes: timestamps become dates, and JPJ's per-car registration records are summed per month.
- `public/data/catalogue.json` describes every table and column in English and Malay, using
  data.gov.my's own data dictionaries, plus code labels (CPI divisions, GDP sectors, SITC sections)
  and fixes where the published description is wrong (see `FIXED_FIELDS` in `etl/build.py`).

## Evals

`evals/seed-questions.md` holds 50 starting questions (22 EN, 17 BM, 11 rojak). `evals/gold.py`
has the reference SQL for each one, and `evals/coverage.md` shows what the data answers:
40 fully, 2 with a caveat, 4 not covered (trade by country or state, urban share), and
4 that should be refused.

`evals/run_model.mjs` sends each question through the same engine and checks the numbers it gets
against the reference answers. Runs are kept in `evals/results/`:

| Run (2026-10-27) | Score | What changed |
|---|---|---|
| 1 | 42/50 (84%) | first full run, Gemma 4 26B, thinking off |
| 2 | 44/50 (88%) | long results sampled across the period; refuse missing breakdowns; SQL-check bug fixed |
| 3 | 46/50 (92%) | clearer rules for dates, ratios and comparisons; better table descriptions |
| 4 | 48/50 (96%) | retry when a query never filters by date |

These 50 questions were also used to tune the prompts, so 96% flatters the engine. The next
milestone adds a larger, held-out question set for an honest score.

## Licence

Code: MIT. Data: © the publishing agencies via data.gov.my, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
