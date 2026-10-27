"""Reference answers for the seed questions: the SQL a correct system would run.

Each entry: id, question, lang, status, sql (if answerable), note.
status: ok · partial (answerable with a caveat the answer must state) · gap (no data in v1) · refuse
Tables are referenced by catalogue id; run.py maps each id to public/data/<id>.parquet.
"""

P = "date = (SELECT max(date) FROM {t})"  # latest date in table {t}

Q = [
    dict(id=1, lang="EN", status="ok", question="What is the population of Selangor?",
         sql="""SELECT date, population * 1000 AS people FROM population_state
                WHERE state = 'Selangor' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                ORDER BY date DESC LIMIT 1"""),
    dict(id=2, lang="EN", status="ok", question="Which state has the highest median household income?",
         sql="""SELECT date, state, income_median FROM hh_income_state
                WHERE date = (SELECT max(date) FROM hh_income_state)
                ORDER BY income_median DESC LIMIT 1"""),
    dict(id=3, lang="EN", status="ok", question="How has Malaysia's unemployment rate changed since 2019?",
         sql="""SELECT year(date) AS year, round(avg(u_rate), 2) AS avg_u_rate FROM lfs_month
                WHERE date >= '2019-01-01' GROUP BY 1 ORDER BY 1""",
         note="Trend; annual averages of the monthly rate. Monthly series also acceptable."),
    dict(id=4, lang="EN", status="ok", question="What was the inflation rate last month?",
         sql="""SELECT date, inflation_yoy FROM cpi_headline_inflation
                WHERE division = 'overall' ORDER BY date DESC LIMIT 1""",
         note="'Last month' = latest month published."),
    dict(id=5, lang="EN", status="ok", question="Which district in Sabah has the most people?",
         sql="""SELECT date, district, population * 1000 AS people FROM population_district
                WHERE state = 'Sabah' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                  AND date = (SELECT max(date) FROM population_district)
                ORDER BY population DESC LIMIT 1"""),
    dict(id=6, lang="EN", status="ok", question="How many babies were born in Malaysia in 2023?",
         sql="SELECT abs AS births FROM births_annual WHERE year(date) = 2023"),
    dict(id=7, lang="EN", status="ok", question="Compare the mean household income of Kelantan and Kuala Lumpur.",
         sql="""SELECT date, state, income_mean FROM hh_income_state
                WHERE state IN ('Kelantan', 'W.P. Kuala Lumpur')
                  AND date = (SELECT max(date) FROM hh_income_state) ORDER BY state"""),
    dict(id=8, lang="EN", status="gap", question="What are Malaysia's top 5 export partners?",
         note="No trade-by-country table on data.gov.my. Answer should say so and offer total or by-product exports."),
    dict(id=9, lang="EN", status="ok", question="Show the poverty rate by state on a map.",
         sql="""SELECT date, state, poverty_absolute FROM hh_poverty_state
                WHERE date = (SELECT max(date) FROM hh_poverty_state) ORDER BY state""",
         note="Map. Absolute poverty is the headline rate."),
    dict(id=10, lang="EN", status="ok", question="How much has food inflation risen over the past 3 years?",
         sql="""WITH f AS (SELECT date, index FROM cpi_headline WHERE division = '01')
                SELECT (SELECT max(date) FROM f) AS latest,
                       round(100 * ((SELECT index FROM f ORDER BY date DESC LIMIT 1) /
                                    (SELECT index FROM f WHERE date = (SELECT max(date) FROM f) - INTERVAL 36 MONTH) - 1), 1) AS pct_change""",
         note="Cumulative change in the food price index over 36 months."),
    dict(id=11, lang="EN", status="ok", question="What share of Malaysia's population is over 65?",
         sql="""SELECT date, round(100 * sum(population) FILTER (WHERE age IN ('65-69','70-74','75-79','80-84','85+'))
                              / sum(population) FILTER (WHERE age = 'overall'), 1) AS pct_65_plus
                FROM population_malaysia
                WHERE sex = 'both' AND ethnicity = 'overall' AND date = (SELECT max(date) FROM population_malaysia)
                GROUP BY date""",
         note="'Over 65' read as 65 and older (the age groups start at 65)."),
    dict(id=12, lang="EN", status="ok", question="Which state's GDP grew fastest in the last 5 years?",
         sql="""WITH g AS (SELECT state, date, value FROM gdp_state_real_supply
                           WHERE series = 'abs' AND sector = 'p0' AND state <> 'Supra')
                SELECT a.state, round(100 * (a.value / b.value - 1), 1) AS pct_growth
                FROM g a JOIN g b ON a.state = b.state AND b.date = a.date - INTERVAL 5 YEAR
                WHERE a.date = (SELECT max(date) FROM g) ORDER BY pct_growth DESC LIMIT 1""",
         note="Real GDP (constant 2015 prices)."),
    dict(id=13, lang="EN", status="ok", question="What is the price of RON95 petrol this week?",
         sql="""SELECT date, ron95, ron95_budi95 FROM fuelprice
                WHERE series_type = 'level' ORDER BY date DESC LIMIT 1""",
         note="Answer should give both the unsubsidised and the BUDI95 subsidised price."),
    dict(id=14, lang="EN", status="ok", question="How many new cars were registered in 2024?",
         sql="""SELECT sum(registrations) AS cars FROM registrations_type_fuel
                WHERE year(date) = 2024 AND type = 'car' AND fuel = 'all_fuels'"""),
    dict(id=15, lang="EN", status="ok", question="Is the population of Perlis growing or shrinking?",
         sql="""SELECT date, population * 1000 AS people FROM population_state
                WHERE state = 'Perlis' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                  AND date >= (SELECT max(date) FROM population_state) - INTERVAL 10 YEAR ORDER BY date"""),
    dict(id=16, lang="EN", status="ok", question="Which state has the lowest unemployment rate?",
         sql="""SELECT date, state, u_rate FROM lfs_qtr_state
                WHERE date = (SELECT max(date) FROM lfs_qtr_state) ORDER BY u_rate ASC LIMIT 1""",
         note="Latest quarter."),
    dict(id=17, lang="EN", status="ok", question="What is GDP per person in Penang compared to the national figure?",
         sql="""WITH y AS (SELECT max(date) AS d FROM gdp_state_real_supply)
                SELECT (SELECT d FROM y) AS date,
                  round((SELECT value FROM gdp_state_real_supply, y WHERE series = 'abs' AND sector = 'p0'
                         AND state = 'Pulau Pinang' AND date = d) * 1e6 /
                        (SELECT population * 1000 FROM population_state, y WHERE state = 'Pulau Pinang' AND sex = 'both'
                         AND age = 'overall' AND ethnicity = 'overall' AND date = d)) AS penang_gdp_per_person,
                  (SELECT round(gdp_capita) FROM gdp_gni_annual_real, y WHERE series = 'abs' AND CAST(date AS DATE) = d) AS national_gdp_per_person""",
         note="Joins two tables; real 2015 prices for both."),
    dict(id=18, lang="EN", status="ok", question="How did the ringgit move against the US dollar this year?",
         sql="""SELECT date, USD FROM exchangerates WHERE indicator = 'avg'
                  AND year(date) = (SELECT year(max(date)) FROM exchangerates) ORDER BY date""",
         note="RM per US$1; a falling number means the ringgit strengthened."),
    dict(id=19, lang="EN", status="ok", question="Which state has the highest income inequality (Gini)?",
         sql="""SELECT date, state, gini FROM hh_inequality_state
                WHERE date = (SELECT max(date) FROM hh_inequality_state) ORDER BY gini DESC LIMIT 1"""),
    dict(id=20, lang="EN", status="gap", question="Total imports from China in 2024?",
         note="No trade-by-country table. Answer should say so."),
    dict(id=21, lang="BM", status="ok", question="Berapa jumlah penduduk Johor?",
         sql="""SELECT date, population * 1000 AS people FROM population_state
                WHERE state = 'Johor' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                ORDER BY date DESC LIMIT 1"""),
    dict(id=22, lang="BM", status="ok", question="Negeri mana pendapatan isi rumah naik paling laju sejak 2019?",
         sql="""WITH h AS (SELECT state, date, income_median FROM hh_income_state)
                SELECT a.state, round(100 * (a.income_median / b.income_median - 1), 1) AS pct_growth
                FROM h a JOIN h b ON a.state = b.state AND year(b.date) = 2019
                WHERE a.date = (SELECT max(date) FROM h) ORDER BY pct_growth DESC LIMIT 1""",
         key=["state"],
         note="Median income, 2019 survey vs latest survey. Mean income is a fair reading too (also Selangor), so only the state is graded."),
    dict(id=23, lang="BM", status="ok", question="Kadar pengangguran belia di Malaysia sekarang berapa?",
         sql="SELECT date, u_rate_15_24, u_rate_15_30 FROM lfs_month_youth ORDER BY date DESC LIMIT 1",
         note="Give both youth definitions (15-24 and 15-30)."),
    dict(id=24, lang="BM", status="ok", question="Berapa kadar inflasi di Sabah tahun lepas?",
         sql="""WITH s AS (SELECT year(date) AS y, avg(index) AS idx FROM cpi_state
                           WHERE state = 'Sabah' AND division = 'overall' GROUP BY 1)
                SELECT a.y AS year, round(100 * (a.idx / b.idx - 1), 1) AS inflation
                FROM s a JOIN s b ON b.y = a.y - 1
                WHERE a.y = year(current_date) - 1""",
         note="Annual inflation = average index of the year vs the year before."),
    dict(id=25, lang="BM", status="ok", question="Daerah mana di Selangor yang paling ramai penduduk?",
         sql="""SELECT date, district, population * 1000 AS people FROM population_district
                WHERE state = 'Selangor' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                  AND date = (SELECT max(date) FROM population_district)
                ORDER BY population DESC LIMIT 1"""),
    dict(id=26, lang="BM", status="ok", question="Berapa ramai kematian di Malaysia pada tahun 2022?",
         sql="SELECT abs AS deaths FROM deaths WHERE year(date) = 2022"),
    dict(id=27, lang="BM", status="ok", question="Bandingkan kadar kemiskinan Kelantan dan Terengganu.",
         sql="""SELECT date, state, poverty_absolute FROM hh_poverty_state
                WHERE state IN ('Kelantan', 'Terengganu') AND date = (SELECT max(date) FROM hh_poverty_state)
                ORDER BY state"""),
    dict(id=28, lang="BM", status="ok", question="Harga minyak diesel naik berapa banyak tahun ini?",
         sql="""WITH f AS (SELECT date, diesel FROM fuelprice WHERE series_type = 'level'),
                     y AS (SELECT year(max(date)) AS yr FROM f)
                SELECT (SELECT diesel FROM f, y WHERE year(date) = yr ORDER BY date ASC LIMIT 1) AS first_price_this_year,
                       (SELECT diesel FROM f ORDER BY date DESC LIMIT 1) AS latest_price""",
         note="Peninsular diesel; may have fallen rather than risen."),
    dict(id=29, lang="BM", status="ok", question="Tunjukkan nisbah lelaki dan perempuan mengikut negeri.",
         sql="""SELECT state, round(100 * sum(population) FILTER (WHERE sex = 'male')
                                  / sum(population) FILTER (WHERE sex = 'female'), 1) AS males_per_100_females
                FROM population_state
                WHERE age = 'overall' AND ethnicity = 'overall' AND date = (SELECT max(date) FROM population_state)
                GROUP BY state ORDER BY state""",
         note="Map."),
    dict(id=30, lang="BM", status="partial", question="Berapa nilai eksport minyak sawit Malaysia tahun lepas?",
         sql="""SELECT sum(exports) AS rm FROM trade_sitc_1d
                WHERE section = '4' AND year(date) = year(current_date) - 1""",
         note="Only SITC section 4 (all animal & vegetable oils and fats) exists; answer must say palm oil is most of it but not all."),
    dict(id=31, lang="BM", status="ok", question="Negeri mana kadar kelahiran paling rendah?",
         sql="""SELECT date, state, rate FROM births_annual_state
                WHERE date = (SELECT max(date) FROM births_annual_state) ORDER BY rate ASC LIMIT 1""",
         note="Crude birth rate per 1,000 people."),
    dict(id=32, lang="BM", status="ok", question="Purata perbelanjaan isi rumah sebulan di Kuala Lumpur?",
         sql="""SELECT date, expenditure_mean FROM hies_state
                WHERE state = 'W.P. Kuala Lumpur' ORDER BY date DESC LIMIT 1"""),
    dict(id=33, lang="BM", status="gap", question="Berapa peratus rakyat Malaysia tinggal di bandar?",
         note="Population tables have no urban/rural split in v1."),
    dict(id=34, lang="BM", status="ok", question="Adakah inflasi makanan lebih tinggi daripada inflasi keseluruhan?",
         sql="""SELECT date, division, inflation_yoy FROM cpi_headline_inflation
                WHERE division IN ('01', 'overall') AND date = (SELECT max(date) FROM cpi_headline_inflation)
                ORDER BY division""",
         key=["inflation_yoy"], note="Graded on the two rates; they can come back as one row or two."),
    dict(id=35, lang="BM", status="ok", question="Pendapatan median isi rumah di Pahang berapa?",
         sql="""SELECT date, income_median FROM hh_income_state WHERE state = 'Pahang' ORDER BY date DESC LIMIT 1"""),
    dict(id=36, lang="BM", status="ok", question="Negeri mana paling ramai orang tua?",
         sql="""SELECT state, sum(population) * 1000 AS people_65_plus FROM population_state
                WHERE age IN ('65-69','70-74','75-79','80-84','85+') AND sex = 'both' AND ethnicity = 'overall'
                  AND date = (SELECT max(date) FROM population_state)
                GROUP BY state ORDER BY people_65_plus DESC LIMIT 1""",
         note="Ambiguous: 'paling ramai' = most people aged 65+ (count). A share-based answer should say which it uses."),
    dict(id=37, lang="rojak", status="ok", question="Berapa ramai orang kat Sarawak sekarang?",
         sql="""SELECT date, population * 1000 AS people FROM population_state
                WHERE state = 'Sarawak' AND sex = 'both' AND age = 'overall' AND ethnicity = 'overall'
                ORDER BY date DESC LIMIT 1"""),
    dict(id=38, lang="rojak", status="ok", question="Gaji median Malaysia naik ke tak dari tahun lepas?",
         sql="""SELECT date, wages_median FROM wages_state WHERE state = 'Malaysia' AND sex = 'both'
                ORDER BY date DESC LIMIT 2"""),
    dict(id=39, lang="rojak", status="ok", question="KL ke Selangor yang household income lagi tinggi?",
         sql="""SELECT date, state, income_median, income_mean FROM hh_income_state
                WHERE state IN ('W.P. Kuala Lumpur', 'Selangor') AND date = (SELECT max(date) FROM hh_income_state)
                ORDER BY state"""),
    dict(id=40, lang="rojak", status="ok", question="Unemployment rate Penang berapa eh?",
         sql="SELECT date, u_rate FROM lfs_qtr_state WHERE state = 'Pulau Pinang' ORDER BY date DESC LIMIT 1"),
    dict(id=41, lang="rojak", status="ok", question="Barang makanan naik harga berapa percent this year?",
         sql="""SELECT date, inflation_yoy FROM cpi_headline_inflation WHERE division = '01'
                ORDER BY date DESC LIMIT 1""",
         note="Ambiguous: year-on-year food inflation; a year-to-date change is also acceptable if stated."),
    dict(id=42, lang="rojak", status="gap", question="Mana state paling banyak export?",
         note="No trade-by-state table."),
    dict(id=43, lang="rojak", status="ok", question="Boleh show map kemiskinan ikut daerah?",
         sql="""SELECT date, state, district, poverty_absolute FROM hh_poverty_district
                WHERE date = (SELECT max(date) FROM hh_poverty_district) ORDER BY state, district""",
         note="District map."),
    dict(id=44, lang="rojak", status="ok", question="Petrol RON97 sekarang berapa ringgit?",
         sql="SELECT date, ron97 FROM fuelprice WHERE series_type = 'level' ORDER BY date DESC LIMIT 1"),
    dict(id=45, lang="rojak", status="partial", question="Kereta baru registered paling banyak kat negeri mana?",
         sql="""SELECT state, sum(registrations) AS cars FROM cars_monthly
                WHERE year(date) = year(current_date) - 1 AND state <> 'Rakan Niaga'
                GROUP BY state ORDER BY cars DESC LIMIT 1""",
         key=["state"],
         note="Most cars are registered via JPJ's dealer portal ('Rakan Niaga'), not a state office: answer must say so. No period named, so a latest-month answer is fair; only the state is graded."),
    dict(id=46, lang="rojak", status="ok", question="Population growth Malaysia slow down ke since COVID?",
         sql="""WITH p AS (SELECT date, population FROM population_malaysia
                           WHERE sex = 'both' AND age = 'overall' AND ethnicity = 'overall')
                SELECT year(a.date) AS year, round(100 * (a.population / b.population - 1), 2) AS growth_pct
                FROM p a JOIN p b ON b.date = a.date - INTERVAL 1 YEAR
                WHERE a.date >= '2015-01-01' ORDER BY 1"""),
    dict(id=47, lang="EN", status="refuse", question="Who will win the next general election?", note="Opinion / forecast."),
    dict(id=48, lang="BM", status="refuse", question="Berapa harga rumah di Shah Alam tahun 2030?", note="Forecast; also no house price data."),
    dict(id=49, lang="EN", status="refuse", question="What is the population of Singapore?", note="Not Malaysian data."),
    dict(id=50, lang="rojak", status="refuse", question="Gaji aku cukup ke untuk beli rumah kat KL?", note="Personal financial advice."),
]
