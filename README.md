# angka

Ask a question about Malaysia in BM, English or rojak and get an answer computed from official
open data, with the dataset it came from and the SQL that produced it.

> Work in progress. M1 (data) is done; the question box, model and site come next.

## How it works (planned)

1. An open model on Cloudflare Workers AI reads the catalogue and writes one DuckDB SQL query.
2. The query runs in your browser with DuckDB-WASM over small Parquet files.
3. The answer comes back in the language you asked in, with a chart or map and links to the source.

The model never states a number itself: every number is computed by DuckDB from the data.

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

## Licence

Code: MIT. Data: © the publishing agencies via data.gov.my, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
