# Seed questions — v0 (written by Claude, 2026-10-27)

Starting set for M1: decides which ~25 datasets to load, and becomes the first slice of the
eval set. These are written by Claude, so they are biased toward what the data can answer —
mix in real questions from people before the catalogue is final.

Type: `single` one number · `rank` top/bottom · `trend` over time · `compare` two things ·
`multi` needs two datasets · `map` best shown on the state/district map · `no` should be refused.

| # | Question | Lang | Type | Dataset area |
|---|---|---|---|---|
| 1 | What is the population of Selangor? | EN | single | population by state |
| 2 | Which state has the highest median household income? | EN | rank/map | household income (HIES) |
| 3 | How has Malaysia's unemployment rate changed since 2019? | EN | trend | labour force |
| 4 | What was the inflation rate last month? | EN | single | CPI |
| 5 | Which district in Sabah has the most people? | EN | rank | population by district |
| 6 | How many babies were born in Malaysia in 2023? | EN | single | births |
| 7 | Compare the mean household income of Kelantan and Kuala Lumpur. | EN | compare | household income |
| 8 | What are Malaysia's top 5 export partners? | EN | rank | trade by country |
| 9 | Show the poverty rate by state on a map. | EN | map | poverty |
| 10 | How much has food inflation risen over the past 3 years? | EN | trend | CPI by division |
| 11 | What share of Malaysia's population is over 65? | EN | single | population by age |
| 12 | Which state's GDP grew fastest in the last 5 years? | EN | rank | GDP by state |
| 13 | What is the price of RON95 petrol this week? | EN | single | fuel prices |
| 14 | How many new cars were registered in 2024? | EN | single | vehicle registrations |
| 15 | Is the population of Perlis growing or shrinking? | EN | trend | population by state |
| 16 | Which state has the lowest unemployment rate? | EN | rank/map | labour force by state |
| 17 | What is GDP per person in Penang compared to the national figure? | EN | compare | GDP by state + population |
| 18 | How did the ringgit move against the US dollar this year? | EN | trend | exchange rates |
| 19 | Which state has the highest income inequality (Gini)? | EN | rank | household income |
| 20 | Total imports from China in 2024? | EN | single | trade by country |
| 21 | Berapa jumlah penduduk Johor? | BM | single | population by state |
| 22 | Negeri mana pendapatan isi rumah naik paling laju sejak 2019? | BM | multi/rank | household income 2019 vs 2022 |
| 23 | Kadar pengangguran belia di Malaysia sekarang berapa? | BM | single | labour force by age |
| 24 | Berapa kadar inflasi di Sabah tahun lepas? | BM | single | CPI by state |
| 25 | Daerah mana di Selangor yang paling ramai penduduk? | BM | rank/map | population by district |
| 26 | Berapa ramai kematian di Malaysia pada tahun 2022? | BM | single | deaths |
| 27 | Bandingkan kadar kemiskinan Kelantan dan Terengganu. | BM | compare | poverty |
| 28 | Harga minyak diesel naik berapa banyak tahun ini? | BM | trend | fuel prices |
| 29 | Tunjukkan nisbah lelaki dan perempuan mengikut negeri. | BM | map | population by sex |
| 30 | Berapa nilai eksport minyak sawit Malaysia tahun lepas? | BM | single | trade by product |
| 31 | Negeri mana kadar kelahiran paling rendah? | BM | rank/map | births + population |
| 32 | Purata perbelanjaan isi rumah sebulan di Kuala Lumpur? | BM | single | household expenditure |
| 33 | Berapa peratus rakyat Malaysia tinggal di bandar? | BM | single | population urban/rural |
| 34 | Adakah inflasi makanan lebih tinggi daripada inflasi keseluruhan? | BM | compare | CPI by division |
| 35 | Pendapatan median isi rumah di Pahang berapa? | BM | single | household income |
| 36 | Negeri mana paling ramai orang tua? | BM | rank/map | population by age |
| 37 | Berapa ramai orang kat Sarawak sekarang? | rojak | single | population by state |
| 38 | Gaji median Malaysia naik ke tak dari tahun lepas? | rojak | trend | salaries & wages |
| 39 | KL ke Selangor yang household income lagi tinggi? | rojak | compare | household income |
| 40 | Unemployment rate Penang berapa eh? | rojak | single | labour force by state |
| 41 | Barang makanan naik harga berapa percent this year? | rojak | trend | CPI by division |
| 42 | Mana state paling banyak export? | rojak | rank | trade by state |
| 43 | Boleh show map kemiskinan ikut daerah? | rojak | map | poverty by district |
| 44 | Petrol RON97 sekarang berapa ringgit? | rojak | single | fuel prices |
| 45 | Kereta baru registered paling banyak kat negeri mana? | rojak | rank | vehicle registrations |
| 46 | Population growth Malaysia slow down ke since COVID? | rojak | trend | population + births/deaths |
| 47 | Who will win the next general election? | EN | no | — (opinion/forecast) |
| 48 | Berapa harga rumah di Shah Alam tahun 2030? | BM | no | — (forecast) |
| 49 | What is the population of Singapore? | EN | no | — (not Malaysian data) |
| 50 | Gaji aku cukup ke untuk beli rumah kat KL? | rojak | no | — (personal advice) |

Mix: 22 EN · 17 BM · 11 rojak. Four refusals (#47–50), one per kind: opinion, forecast, non-Malaysian data, personal advice.
