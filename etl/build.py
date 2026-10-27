"""Build angka's data: download the chosen OpenDOSM / data.gov.my datasets, tidy them into
small Parquet files under public/data/, and write public/data/catalogue.json — the description
of every table that the model reads before it writes SQL.

    uv run python etl/build.py

It reads each dataset's metadata (titles, column meanings, units, in English and Malay) from
github.com/data-gov-my/datagovmy-meta, cloned into data/raw/ on first run (or pass --meta).

The source tables are kept as published (same columns, same values) so every number can be
traced back to data.gov.my. The only changes: timestamps become dates, and the car registration
records are summed per month (the raw files are ~800k rows a year).
"""

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "data"
META_REPO = "https://github.com/data-gov-my/datagovmy-meta.git"
META_DIR = ROOT / "data" / "raw" / "datagovmy-meta"

# id on data.gov.my -> why it is in v1 (the seed questions it answers)
DATASETS = {
    "population_malaysia": "national population by sex, age, ethnicity",
    "population_state": "population by state (Q1, Q15, Q21, Q29, Q36, Q37)",
    "population_district": "population by district (Q5, Q25)",
    "births_annual": "national births (Q6)",
    "births_annual_state": "births by state (Q31)",
    "deaths": "national deaths (Q26)",
    "deaths_state": "deaths by state",
    "hh_income": "national household income (all income of a household, pendapatan isi rumah) over time; not salaries",
    "hh_income_state": "household income (pendapatan isi rumah) by state over time; not salaries (Q2, Q7, Q22, Q35, Q39)",
    "hies_state": "income, spending, Gini, poverty by state (Q32)",
    "hies_district": "income, spending, Gini, poverty by district",
    "hh_inequality_state": "Gini by state over time (Q19)",
    "hh_poverty_state": "poverty by state over time (Q9, Q27)",
    "hh_poverty_district": "poverty by district (Q43)",
    "cpi_headline": "consumer price index by category (food, transport, housing and 10 more) and overall; price changes over any period (Q10, Q41)",
    "cpi_headline_inflation": "inflation rate, overall and by category such as food (inflasi makanan), transport, housing (Q4, Q34)",
    "cpi_state": "consumer price index by state and category, for yearly inflation by state (Q24)",
    "cpi_state_inflation": "monthly inflation rate by state and category",
    "lfs_month": "monthly unemployment (Q3)",
    "lfs_month_youth": "youth unemployment (Q23)",
    "lfs_qtr_state": "unemployment by state (Q16, Q40)",
    "wages_state": "salaries and wages of employees (gaji, upah), by state and for Malaysia as a whole (Q38)",
    "gdp_state_real_supply": "GDP by state and sector (Q12, Q17)",
    "gdp_gni_annual_real": "national GDP and GDP per capita",
    "gdp_qtr_real": "quarterly GDP growth",
    "trade_headline": "total exports, imports, trade balance",
    "trade_sitc_1d": "exports and imports by product section (Q30, partial)",
    "exchangerates": "ringgit exchange rates (Q18)",
    "fuelprice": "petrol and diesel prices (Q13, Q28, Q44)",
    "registrations_type_fuel": "vehicle registrations by type and fuel (Q14)",
}

# Built here from data.gov.my's daily car registration files (cars_YYYY.parquet).
CARS_FIRST_YEAR = 2015
CARS = {
    "id": "cars_monthly",
    "title_en": "Monthly New Car Registrations by State, Maker & Fuel",
    "title_ms": "Pendaftaran Kereta Baharu Bulanan mengikut Negeri, Pengeluar & Bahan Api",
    "description_en": f"New car registrations summed per month from JPJ's registration records (data.gov.my 'Car Registration Transactions'), {CARS_FIRST_YEAR} onwards. Most cars are registered through JPJ's dealer portal, recorded as state 'Rakan Niaga', which is not a state: leave it out of any by-state answer and say so.",
    "description_ms": f"Pendaftaran kereta baharu dijumlahkan setiap bulan daripada rekod pendaftaran JPJ (data.gov.my 'Car Registration Transactions'), dari {CARS_FIRST_YEAR}.",
    "source_id": "registration_transactions_car",
    "frequency": "MONTHLY",
}

# Columns data.gov.my documents only generically, or not at all.
EXTRA_FIELDS = {
    "fuelprice": {
        "diesel_skds": "[Float] Price per litre of diesel under the SKDS subsidised diesel scheme, in RM (column not documented on data.gov.my)",
        "diesel_budi": "[Float] Price per litre of diesel under the BUDI diesel subsidy, in RM (column not documented on data.gov.my)",
    },
}
CURRENCY_NOTE = "[Float] Ringgit per 1 unit of this currency (3-letter code), e.g. USD 4.07 means RM4.07 per US$1. Filter 'indicator' to one computation (usually 'avg')."

# The SITC section codes have no lookup table on data.gov.my; these are the UN SITC Rev.4 sections.
SITC = {
    "0": ("Food and live animals", "Makanan dan binatang hidup"),
    "1": ("Beverages and tobacco", "Minuman dan tembakau"),
    "2": ("Crude materials, inedible, except fuels", "Bahan mentah, tidak boleh dimakan, kecuali bahan api"),
    "3": ("Mineral fuels, lubricants and related materials", "Bahan api mineral, pelincir dan bahan berkaitan"),
    "4": ("Animal and vegetable oils, fats and waxes (incl. palm oil)", "Minyak dan lemak haiwan dan sayuran (termasuk minyak sawit)"),
    "5": ("Chemicals and related products", "Bahan kimia dan keluaran berkaitan"),
    "6": ("Manufactured goods classified chiefly by material", "Barang perkilangan dikelaskan mengikut bahan"),
    "7": ("Machinery and transport equipment", "Jentera dan kelengkapan pengangkutan"),
    "8": ("Miscellaneous manufactured articles", "Pelbagai barang perkilangan"),
    "9": ("Commodities and transactions not classified elsewhere", "Komoditi dan urus niaga tidak dikelaskan di tempat lain"),
    "overall": ("All sections", "Semua seksyen"),
}

MAX_LISTED_VALUES = 60  # categorical columns with at most this many values get them listed


def connect():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    return con


def lookups(con, meta):
    """Code -> (English, Malay) labels for the coded columns."""
    mcoicop = json.loads((meta / "mcoicop.json").read_text())["link_parquet"]
    cpi = {
        d: (en.strip(), ms.strip())
        for d, en, ms in con.execute(
            f"SELECT division, desc_en, desc_bm FROM read_parquet('{mcoicop}') WHERE digits = 2"
        ).fetchall()
    }
    cpi["overall"] = ("All items (headline)", "Semua barangan (keseluruhan)")

    gdp_url = json.loads((meta / "gdp_lookup.json").read_text())["link_parquet"]
    gdp_cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{gdp_url}')").fetchall()]
    code, en, ms = gdp_cols[1], gdp_cols[2], gdp_cols[3]
    gdp = {}
    for c, e, m in con.execute(f"SELECT {code}, {en}, {ms} FROM read_parquet('{gdp_url}')").fetchall():
        c, e, m = c.strip(), (e or "").strip(), (m or "").strip()
        # a few rows in the source have the English and Malay text swapped
        if any(w in f" {e} " for w in (" dan ", "Produk ", "Minyak dan")) and " and " in f" {m} ":
            e, m = m, e
        gdp[c] = (e, m)
    return {"division": cpi, "sector": gdp, "section": SITC}


def date_fix(con, src):
    """SELECT list that turns timestamp/varchar date columns into DATE."""
    cols = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
    parts = []
    for name, typ, *_ in cols:
        if name in ("date", "date_reg") and typ != "DATE":
            parts.append(f'CAST("{name}" AS DATE) AS "{name}"')
        else:
            parts.append(f'"{name}"')
    return ", ".join(parts)


def describe(con, path, fields, labels):
    """Column list for the catalogue: type, meaning, and the allowed values of small categoricals."""
    src = f"read_parquet('{path}')"
    out = []
    for name, typ, *_ in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall():
        f = fields.get(name, {})
        if not f and len(name) == 3 and name.isupper() and "<currency_code>" in fields:
            f = {**fields["<currency_code>"], "title_en": name, "title_ms": name, "description_en": CURRENCY_NOTE, "description_ms": CURRENCY_NOTE}
        col = {
            "name": name,
            "type": typ,
            "title_en": f.get("title_en", ""),
            "title_ms": f.get("title_ms", ""),
            "description_en": f.get("description_en", ""),
            "description_ms": f.get("description_ms", ""),
        }
        if typ == "VARCHAR":
            n = con.execute(f'SELECT count(DISTINCT "{name}") FROM {src}').fetchone()[0]
            col["distinct_values"] = n
            if n <= MAX_LISTED_VALUES:
                vals = [v for (v,) in con.execute(f'SELECT DISTINCT "{name}" FROM {src} ORDER BY 1').fetchall()]
                if name in labels:
                    col["values"] = [{"value": v, "en": labels[name].get(v, ("", ""))[0], "ms": labels[name].get(v, ("", ""))[1]} for v in vals]
                else:
                    col["values"] = vals
        elif typ == "DATE":
            lo, hi = con.execute(f'SELECT min("{name}")::VARCHAR, max("{name}")::VARCHAR FROM {src}').fetchone()
            col["min"], col["max"] = lo, hi
        out.append(col)
    return out


def sample(con, path, n=3):
    rel = con.execute(f"SELECT * FROM read_parquet('{path}') USING SAMPLE {n} ROWS (reservoir, 42)")
    names = [d[0] for d in rel.description]
    return [{k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in zip(names, row)} for row in rel.fetchall()]


def write(con, select_sql, path):
    con.execute(f"COPY ({select_sql}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)")


# Where data.gov.my's description is wrong. trade_sitc_1d says "RM millions", but its yearly
# 'overall' exports equal trade_headline's (in RM): RM1.61 trillion for 2025.
FIXED_FIELDS = {
    "trade_sitc_1d": {
        "exports": ("[Float] The value of exports in RM (not RM millions, as data.gov.my states).", "[Apung] Nilai eksport dalam RM (bukan RM juta seperti dinyatakan di data.gov.my)."),
        "imports": ("[Float] The value of imports in RM (not RM millions, as data.gov.my states).", "[Apung] Nilai import dalam RM (bukan RM juta seperti dinyatakan di data.gov.my)."),
    },
}


def fields_of(ds_id, m):
    fields = {f["name"]: f for f in m.get("fields", [])}
    for name, text in EXTRA_FIELDS.get(ds_id, {}).items():
        fields.setdefault(name, {"title_en": name, "title_ms": name, "description_en": text, "description_ms": text})
    for name, (en, ms) in FIXED_FIELDS.get(ds_id, {}).items():
        fields[name] = {**fields.get(name, {}), "description_en": en, "description_ms": ms}
    return fields


def entry(con, ds_id, meta_json, path, labels, why):
    m = meta_json
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
    return {
        "id": ds_id,
        "file": f"data/{path.name}",
        "title_en": m.get("title_en", "").strip(),
        "title_ms": m.get("title_ms", "").strip(),
        "description_en": m.get("description_en", "").strip(),
        "description_ms": m.get("description_ms", "").strip(),
        "why": why,
        "frequency": m.get("frequency"),
        "geography": m.get("geography"),
        "source": m.get("data_source"),
        "source_url": f"https://data.gov.my/data-catalogue/{m.get('source_id', ds_id)}",
        "data_as_of": m.get("data_as_of"),
        "caveat_en": (m.get("caveat_en") or "").strip(),
        "rows": rows,
        "bytes": path.stat().st_size,
        "columns": describe(con, path, fields_of(ds_id, m), labels),
        "sample": sample(con, path),
    }


def build(meta):
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    labels = lookups(con, meta)
    catalogue = []

    for ds_id, why in DATASETS.items():
        m = json.loads((meta / f"{ds_id}.json").read_text())
        src = f"read_parquet('{m['link_parquet']}')"
        path = OUT / f"{ds_id}.parquet"
        write(con, f"SELECT {date_fix(con, src)} FROM {src}", path)
        catalogue.append(entry(con, ds_id, m, path, labels, why))
        print(f"  {ds_id}: {catalogue[-1]['rows']:,} rows, {path.stat().st_size / 1024:.0f} KB")

    # Cars: sum the per-registration records into months
    this_year = dt.date.today().year
    car_meta = json.loads((meta / f"{CARS['source_id']}.json").read_text())
    urls = [f"https://storage.data.gov.my/transportation/cars_{y}.parquet" for y in range(CARS_FIRST_YEAR, this_year + 1)]
    path = OUT / f"{CARS['id']}.parquet"
    write(
        con,
        f"""SELECT CAST(date_trunc('month', date_reg) AS DATE) AS date, state, maker, type, fuel,
                   count(*)::INTEGER AS registrations
            FROM read_parquet({urls!r})
            GROUP BY ALL ORDER BY date, state, maker""",
        path,
    )
    fields = {
        "date": {"title_en": "Month", "title_ms": "Bulan", "description_en": "[Date] First day of the month of registration", "description_ms": "[Tarikh] Hari pertama bulan pendaftaran"},
        "registrations": {"title_en": "Registrations", "title_ms": "Pendaftaran", "description_en": "[Integer] Number of new cars registered", "description_ms": "[Integer] Bilangan kereta baharu didaftarkan"},
    }
    for f in car_meta.get("fields", []):
        if f["name"] in ("state", "maker", "type", "fuel"):
            fields[f["name"]] = f
    car_entry = {**car_meta, **CARS, "fields": [{"name": k, **v} for k, v in fields.items()]}
    catalogue.append(entry(con, CARS["id"], car_entry, path, labels, "new car registrations by state and maker (Q45)"))
    print(f"  {CARS['id']}: {catalogue[-1]['rows']:,} rows, {path.stat().st_size / 1024:.0f} KB")

    doc = {
        "built": dt.date.today().isoformat(),
        "licence": "Data from data.gov.my / OpenDOSM, CC BY 4.0. Department of Statistics Malaysia and other agencies as listed per table.",
        "notes": [
            "Tables are kept as published on data.gov.my; only timestamps were turned into dates.",
            "Dates of yearly data are YYYY-01-01; monthly data use the first day of the month.",
            "Many tables mix 'overall' / 'both' total rows with breakdown rows: filter to one level before summing.",
            "Population age groups: the oldest group is '70+' or '80+' for 1970-1990 and '85+' from 1991. An 'aged 65 and over' total must use the groups that exist for that year, and never sum 'overall' with the age groups.",
            "GDP by state puts W.P. Putrajaya inside W.P. Kuala Lumpur and has a 'Supra' row for output not tied to a state.",
        ],
        "tables": catalogue,
    }
    (OUT / "catalogue.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str))
    total = sum(t["bytes"] for t in catalogue)
    print(f"{len(catalogue)} tables, {total / 1024 / 1024:.1f} MB of Parquet -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", type=Path, help="path to datagovmy-meta/data-catalogue (default: clone it into data/raw/)")
    meta = ap.parse_args().meta
    if meta is None:
        if not META_DIR.exists():
            subprocess.run(["git", "clone", "-q", "--depth", "1", META_REPO, str(META_DIR)], check=True)
        else:
            subprocess.run(["git", "-C", str(META_DIR), "pull", "-q", "--ff-only"], check=True)
        meta = META_DIR / "data-catalogue"
    build(meta)
