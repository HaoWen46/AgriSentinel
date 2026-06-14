---
title: "AgriSentinel: Monetizing Fresh Satellite Substrate as Enforcement-Grade Dossiers for Illegal Farmland Factories"
subtitle: "Big Data Systems — Final Project, National Taiwan University (Spring 2026)"
author: "AgriSentinel"
date: "2026-06-15"
---

> **GitHub:** https://github.com/HaoWen46/AgriSentinel
> **Live demo:** _(optional bonus — insert deployed URL here)_
>
> Reproduce everything with `make demo` (live) or `make demo-offline` (no
> network / no API key), then open `http://localhost:8000`.

---

## 0. Thesis in one paragraph

Raw, public, easy data has no durable value: in a competitive market its price
falls to the marginal cost of production, and a 200-line scraper has a marginal
cost near zero. The durable value is in **cognitive labour** — the work a human
analyst does to turn messy inputs into a decision-grade artifact. As of 2026, AI
agents perform that labour at a fraction of the human wage. **AgriSentinel sells
the agent's output artifact — a per-parcel enforcement dossier — not the data
underneath.** The big-data pipeline (multi-temporal satellite imagery fused with
cadastral/zoning data and statute retrieval) exists to feed the agent a substrate
so fresh and well-structured that its dossier beats anything the customer could
get from a generic chatbot. That is what makes the data engineering load-bearing
rather than decorative.

The exploitable asymmetry: **government has authority but no eyes.** It can
lawfully cut water/electricity and demolish illegal farmland structures, but it
does not continuously watch the farmland, so it learns of violations late — after
they harden into pollution or scandal. The technical edge is **collapsing the
observation lag**. There is no luck here (the opposite of finance/alpha-farming):
either the pipeline sees the new structure or it doesn't. The edge is purely
technical capability.

---

## 1. Target Customer (Component 1)

**Primary customer (the whale): county/municipal enforcement units.** In Taiwan,
farmland-factory enforcement sits with 縣市政府 經濟發展局 / 都市發展局 /
環境保護局. They have the **authority** (Factory Management and Counseling Act,
Regional Plan Act) and the **budget**, but lack continuous monitoring. Their job
today is reactive: a citizen reports, an inspector is dispatched, paperwork
(公文) is hand-drafted, and only then can a cut-off/demolition order proceed.

**Beachhead / channel (moves faster): environmental NGOs already in the
workflow** — 地球公民基金會 (Citizens of the Earth Taiwan) and the g0v community
behind **Disfactory** (disfactory.tw). They are the existing "eyes": citizens
report suspected factories, and CET files the paperwork that pressures local
governments. They even crowdsource *detection* through a game, **大家來找廠**,
where volunteers eyeball aerial imagery to spot new buildings on farmland. That
manual visual change-detection, plus the manual drafting of enforcement
paperwork, is exactly the cognitive labour AgriSentinel automates. We do not
invent demand — we replace a crowdsourcing game and hand-written dossiers with a
pipeline, and we ride the NGO→government relationship as the cold-start wedge.

**Why us over the status quo.** The status quo is anonymous citizen reports + a
volunteer game + manual paperwork: slow, unsystematic, and unscalable across
~50,000 sites. We deliver systematic, island-scalable detection **plus** a
ready-to-file dossier per parcel — the same output an inspector would assemble by
hand, produced in seconds.

**Who we explicitly do *not* target:** the factory operators (adversaries), and
the general public (no willingness to pay). The wedge is one county pilot, sold
through the NGO channel, before island scale.

---

## 2. Evidence of Demand and Willingness to Pay (Component 2)

We document the **process**, not just the conclusion. All collection scripts are
in `scripts/demand/` and are reproducible.

### 2.1 The problem is real and growing (reproducible)

`scripts/demand/disfactory_stats.py` pulls reported suspected-factory records
from the Disfactory public API around the pilot AOI and buckets them by report
year. A representative run (7 km radius around 和美鎮, retrieved 2026-06):

| Year | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|
| Reports near AOI | 6 | 14 | 28 | 14 | 21 | 10 | 7 |

*100 reports within 12 km of one township alone*, sustained year after year
(*2026 partial). Cross-checked against the public island-wide figures: **~50,000**
illegal factories on Taiwan's farmland, **3,000–6,000 new per year**, **~1,500 ha
of farmland lost per year** (CET reporting; Disfactory; MOEA unregistered-factory
statistics — re-verify and cite at submission). The chart and CSV are written to
`outputs/demand/`.

### 2.2 The manual-labour baseline we replace

The cognitive labour has two halves, both currently human:

1. **Detection** — the 大家來找廠 volunteer game: a person reviews aerial chips
   and decides whether a new building appeared. At a conservative ~1–2 minutes of
   careful review per image and tens of thousands of parcels to re-check each
   cycle, the volunteer-hours are substantial and unscalable.
2. **Dossier drafting** — CET / county staff hand-assemble the parcel number
   (地號), zoning status, evidence, the specific statute, and a recommended
   action into filing-ready paperwork.

AgriSentinel automates (1) outright and reduces (2) to *human review of a
pre-drafted dossier*. The survey instrument (`survey_questions.md`) quantifies
both: time-per-case for staff (Instrument A, Q4–Q5) and minutes-per-image for
volunteers (Instrument B, Q2–Q6) — the non-monetary willingness-to-pay (time
saved).

### 2.3 Published willingness to pay (reproducible)

Government WTP is **public record**. `scripts/demand/tender_search.py` searches
Taiwan's e-procurement (政府電子採購網) via the g0v PCC API for monitoring /
remote-sensing / illegal-use keywords. A representative run returned **370
matching tenders** across keywords:

| Keyword | 違章工廠 | 農地違規 | 航遙測 | 遙測影像 | 衛星影像 | 國土監測 | 無人機 監測 |
|---|---|---|---|---|---|---|---|
| Matches | 5 | 21 | 100† | 100† | 100† | 10 | 31 |

†page-capped at 100 — the true counts are higher. Government bodies already
procure aerial/remote-sensing and land-monitoring services at scale; we attach to
an existing budget line, not a hypothetical one. (Award amounts live on each
tender's detail page; the script captures volume and recency as the demand
signal, with the commercial comparable below as the price anchor.)

### 2.4 Commercial comparable (the price anchor)

A Japanese commercial service sells satellite + AI farmland monitoring to
municipalities at roughly **¥2,000,000 per municipality (~NT$430,000)**, claiming
**~80% agreement with physical patrols** and **~3 weeks to deploy**. This proves
the *exact* pipeline ships commercially and anchors per-municipality pricing.

### 2.5 The defensible demand claim

> *N* flagged parcels at precision *P* (measured against Disfactory labels, §4.4);
> the incumbent process is manual crowdsourcing + hand-written dossiers;
> comparable monitoring sells at **~NT$430k/municipality**; government already
> procures remote-sensing monitoring (370+ matching tenders). At a cost-per-parcel
> in cents (§5.5), the unit economics close at a handful of municipalities.

---

## 3. System Design

### 3.1 Data sources & ingestion

| Source | What | How |
|---|---|---|
| **Sentinel-2 L2A** (Planetary Computer STAC) | 10 m optical, time-series | `stac_fetch`: STAC search per low-cloud window → least-cloudy scene → windowed COG read of the AOI footprint onto a common 10 m grid → MinIO |
| **Disfactory API** | reported factories (地號, 段, status) | `labels_fetch`: radius query around AOI centre → clip to bbox → PostGIS (the evaluation ground truth) |
| **Parcels / zoning** | farmland polygons + 地號 | `parcels_load`: NLSC land-use / GeoJSON, or a deterministic synthetic grid (full vector cadastre is application-gated — see §6) |
| **Statutes** (全國法規資料庫) | 工輔法, 區域計畫法, 非都市土地使用管制規則, 農業發展條例 | `laws_fetch`: curated article corpus → chunk → embed → pgvector |

A key efficiency: Sentinel-2 assets are **Cloud-Optimized GeoTIFFs**, so
`stac_fetch` issues HTTP range requests for only the AOI window (~0.6 MP/band)
instead of the full ~110 MP scene — this is what keeps the volume tractable on a
laptop while remaining honestly "big data" (the archive compounds every cycle).

### 3.2 Storage & processing — and why each tool fits the shape of the data

- **MinIO (S3) + COG** — the raw lake: immutable raster zone, lakehouse pattern;
  variety (rasters, manifests) and volume.
- **PostGIS + pgvector** — one store, two jobs: GIST-indexed spatial joins decide
  *is this farmland?* (`ST_Intersects`, area in EPSG:3826), and a `vector` column
  serves the statute RAG (`<=>` cosine). Co-locating them removes a moving part.
- **PySpark** (`spark_tiles`) — the batch paradigm: tiles the AOI and maps change
  detection per tile, so the same job scales to many tiles / historical date
  pairs by adding executors. A single-process fallback runs identically without
  Spark.
- **Apache Kafka** (KRaft mode; the shipped compose uses Kafka for CPU
  portability, but any Kafka-API broker such as Redpanda works) — velocity: a
  `detection.completed` event fans out to a worker (which runs join→eval→dossiers)
  and to the dashboard over SSE, so a new imagery date flows to fresh dossiers
  with no manual rerun.

### 3.3 The agent layer (value capture)

`dossier_agent` is the worker that produces the sold artifact. Per flagged
parcel it (1) retrieves the most relevant statute chunks from pgvector, (2) drafts
a **typed, fully-grounded** dossier with Claude (`messages.parse` → schema), and
(3) runs an **adversarial critic** pass that rejects any claim not traceable to a
detection fact or a retrieved statute, revising once. Without an API key it emits
a clearly-labelled rule-based template so the pipeline always completes. Default
model `claude-opus-4-8`; switchable to Sonnet/Haiku for cost at scale.

### 3.4 Delivery

FastAPI serves GeoJSON layers, dossiers, before/after Sentinel-2 RGB chips
(rendered straight from the COGs), and eval metrics; a Leaflet dashboard lets a
grader pick a run, read precision/recall, click a flagged parcel, and see its
imagery + dossier. The architecture diagram is in `README.md` and mirrors §3.

### 3.5 Pipeline phases (each gates the next)

0 infra up · 1 imagery+parcels+labels land · 2 change polygons persisted ·
3 ranked flagged parcels + precision/recall · 4 ≥5 grounded dossiers ·
5 dashboard clickable · 6 new imagery → event → dossier without rerun.

---

## 4. Implementation & Evaluation

### 4.1 Change detection

The default detector is **spectral**: between t0 and t1 it flags pixels where the
built-up index rises (ΔNDBI ≥ 0.06) *and* the vegetation index falls
(ΔNDVI ≥ 0.12) — the signature of construction replacing crops — then vectorises
connected regions ≥ 400 m² into candidate polygons with a confidence score.
Requiring **both** signals suppresses the bare-soil/water false positives a
single-index threshold would trip on (verified on a real Changhua scene: NDVI
ranged −0.21 to 0.62). The interface is swappable: a `torchgeo` Siamese-UNet
(OSCD) path is a documented extension; if selected but unwired it falls back to
spectral with a loud warning. 10 m Sentinel-2 is deliberately used as a
"something changed" detector, to be confirmed with higher-res NLSC orthophotos.

### 4.2 Zoning join — "illegal" = change **+** zoning

A change polygon is only a *candidate violation* once it sits on agricultural
land. `zoning_join` intersects detections with farmland parcels in PostGIS, keeps
only farmland overlaps, attaches the 地號, finds the nearest Disfactory label, and
ranks by confidence into the worklist. We never label a parcel "illegal" without
the zoning overlay.

### 4.3 The agent's grounding guarantee

Every factual claim in a dossier traces to a detection fact or a retrieved
statute chunk; the critic pass exists specifically to catch fabricated parcel
numbers, dates, areas, or citations, and to keep the language at "suspected /
candidate violation pending field verification." The dossier is decision-support,
not a legal ruling, and targets a parcel/structure, never a person.

### 4.4 Evaluation — the credibility anchor

`evaluate` computes precision/recall of flagged detections against Disfactory
labels within a match radius (default 80 m):

- **Precision** = flagged detections within radius of a known label ÷ all flagged.
- **Recall** = known labels with a flagged detection within radius ÷ all labels.

Disfactory labels are crowd-reported and **incomplete**, so these are *indicative,
not absolute* — a flagged parcel with no nearby label may still be a real, simply
unreported, factory (which is precisely the value: surfacing the unreported). The
dashboard shows the live number for the selected run; the offline demo is
constructed so precision and recall are both strictly between 0 and 1 (some
patches have labels, one labelled factory has no detectable patch, and some
detections have no label) — an honest, non-trivial score rather than a staged
100%.

> _Insert the precision/recall/F1 from your run here (printed by `make evaluate`
> and shown on the dashboard)._

---

## 5. Scalability & Cost (10× / 100×)

| Concern | Pilot (1 township) | 10× (1 county) | 100× (national) |
|---|---|---|---|
| Imagery | windowed COG reads, MinIO | same; partition by tile/date | move lake to real S3; Sentinel-1 SAR fusion to beat cloud (`# TODO(scale)`) |
| Compute | single-process / local Spark | Spark on a few executors | Spark cluster; CD per tile is embarrassingly parallel |
| Store | one PostGIS | partition parcels/detections by AOI; PostGIS read replicas | sharded PostGIS + object-store parquet for cold detections |
| Agent | per-parcel Claude calls | prompt-cache the statute corpus; batch API (50% off) | Batch API + Haiku for triage, Opus for high-confidence; cents/parcel |
| Stream | one Kafka broker | partitions per county | multi-broker; consumer groups per region |

**Unit economics.** A dossier is a few thousand tokens of context + output. At
batch/Sonnet pricing that is **on the order of a few US cents per parcel**, versus
monitoring contracts in the hundreds of thousands of NT$ and volunteer-hours per
detection. The compounding moat is the **imagery archive**: every cycle of
snapshots is history a later competitor cannot reproduce.

---

## 6. Go-to-Market Difficulties (Component 3, bonus)

- **Trust / adoption.** Why trust automated detection? Answer with the Phase-3
  precision/recall against known factories, a confidence score on every flag,
  and a **human-in-the-loop review** step before any dossier is filed. The
  product is framed as decision-support, never an automated ruling.
- **Data acquisition cost & licensing.** Sentinel-2 and Disfactory are open
  (CC BY 4.0 cited); statutes are MOJ open data. The real friction is the **NLSC
  vector cadastre** (地籍 WFS), which requires a government/academic application —
  so the demo ships a deterministic synthetic parcel layer (clearly labelled) and
  the production path joins the official farmland/land-use layer once access is
  granted. This gating is itself a moat once we are inside the channel.
- **Legal / ethics / PDPA.** The dossier targets parcels/structures, not persons;
  we avoid naming private individuals and keep "suspected/candidate" language.
- **Don't antagonise the incumbent.** We augment CET/Disfactory's proven workflow
  and the government's authority — leverage, not replacement.
- **Cold start.** Beachhead through the NGO channel; one county pilot before
  island scale; the eval number is the trust-builder that unlocks the first paid
  pilot.
- **Competition & moat.** A scraper of Disfactory is worthless (the data is free);
  the moat is the fused, per-parcel substrate + the inspector-judgment scaffolding
  encoded in the detection→zoning→dossier pipeline + the compounding archive +
  distribution inside the enforcement channel.

---

## 7. Caveats & Honesty

- **Cloud cover.** Taiwan is cloudy; optical Sentinel-2 has gaps. Mitigated with
  low-cloud scene selection and multi-temporal windows; SAR fusion is a noted
  `# TODO(scale)`, not blocking the MVP.
- **Resolution.** 10 m is coarse for small buildings — used as a "something
  changed" trigger, confirmed with higher-res orthophotos.
- **Eval honesty.** Disfactory labels are incomplete; precision/recall are
  indicative. The synthetic parcel/imagery fallback is for offline
  reproducibility and is always labelled as such — never presented as real.

---

## 8. Reproducibility & Deliverables

- **One-command run:** `make demo` (live) / `make demo-offline` (offline).
- **Demand evidence:** `scripts/demand/*` regenerate the numbers in §2.
- **Tests:** `make test` (unit + DB-integration; zoning-join correctness).
- **Code:** all ingestion/processing/agent/delivery layers, runnable `README.md`,
  architecture overview mirroring §3.

## 9. Rubric Map

| Criterion | Weight | Where |
|---|---|---|
| Target customer clarity | 20% | §1 |
| Demand evidence & acquisition | 25% | §2 + `scripts/demand/` |
| Technical system & implementation | 40% | §3–§5 + the repo |
| Writing, diagrams, presentation | 15% | this report + README diagram + dashboard |
| Bonus: GTM difficulties | +10% | §6 |
| Bonus: live deployment | +10% | live URL on page 1 (optional) |
