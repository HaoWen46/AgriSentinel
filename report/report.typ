// AgriSentinel final report (Typst source). Compile:
//   typst compile report/report.typ report/report.pdf
#import "@preview/fletcher:0.5.7" as fletcher: diagram, node, edge

#set document(title: "AgriSentinel", author: "AgriSentinel")
#set page(
  paper: "a4",
  margin: (x: 2cm, y: 2cm),
  numbering: "1",
  footer: context [
    #set text(8pt, fill: rgb("#6b6f63"))
    AgriSentinel · Big Data Systems Final Project, NTU Spring 2026
    #h(1fr) #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: ("Noto Serif CJK TC",), size: 10pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#set smartquote(enabled: false)  // CJK body font renders curly quotes over-wide
#show raw: set text(font: ("DejaVu Sans Mono", "Noto Sans CJK TC"), size: 8pt)
#set heading(numbering: "1.")
#show heading: set text(font: ("Noto Sans CJK TC",))
#show heading.where(level: 1): set text(size: 11.5pt, fill: rgb("#234f2c"))
#show link: set text(fill: rgb("#2f6b3c"))

// Diagram layer helpers.
#let lyr(title, body) = box(width: 13cm)[
  #set align(left)
  #text(font: ("Noto Sans CJK TC",), weight: "bold", size: 9.5pt)[#title]
  #linebreak()
  #text(size: 8pt)[#body]
]
#let elbl(t) = text(7pt, fill: rgb("#5a6b50"), font: ("Noto Sans CJK TC",))[#t]

// ── Title block ──────────────────────────────────────────────────────────────
#align(center)[
  #text(26pt, weight: "bold", font: ("Noto Sans CJK TC",))[AgriSentinel]
  #v(3pt)
  #text(9.5pt, fill: rgb("#3a4034"))[Monetizing Fresh Satellite Substrate as
  Enforcement-Grade Dossiers for Illegal Farmland Factories]
  #v(3pt)
  #text(8.5pt, style: "italic")[Big Data Systems Final Project · National Taiwan University · Spring 2026]
]

#align(center)[
  #box(inset: 8pt, radius: 5pt, fill: rgb("#f4f1ea"), stroke: 0.5pt + rgb("#d9d6c8"))[
    #set text(9pt)
    *GitHub:* #link("https://github.com/HaoWen46/AgriSentinel")[github.com/HaoWen46/AgriSentinel] \
    Reproduce with `make demo` (live) or `make demo-offline` (no network / no API key), then open `localhost:8000`.
  ]
]
#v(4pt)

// ── Abstract ─────────────────────────────────────────────────────────────────
#box(inset: 8pt, radius: 5pt, fill: rgb("#fbfaf4"), stroke: 0.5pt + rgb("#d9d6c8"), width: 100%)[
  *Thesis.* Raw, public, easy data has no durable value: in a competitive market
  its price falls to the marginal cost of production, and a 200-line scraper has a
  marginal cost near zero. The durable value is in *cognitive labour*, the work a
  human analyst does to turn messy inputs into a decision-grade artifact. As of
  2026, AI agents perform that labour at a fraction of the human wage. *AgriSentinel
  sells the agent's output artifact, a per-parcel enforcement dossier, not the data
  underneath.* The big-data pipeline (multi-temporal satellite imagery fused with
  cadastral/zoning data and statute retrieval) exists to feed the agent a substrate
  fresh and well-structured enough that its dossier beats anything the customer
  could get from a generic chatbot. The exploitable asymmetry: *government has
  authority but no eyes.* It can lawfully cut water/electricity and demolish illegal
  farmland structures, but it does not continuously watch the farmland, so it learns
  of violations late. The technical edge is *collapsing the observation lag*, and
  there is no luck in it: either the pipeline sees the new structure or it doesn't.
]

= Target Customer

*Primary customer (the whale): county / municipal enforcement units.* In Taiwan,
farmland-factory enforcement sits with 縣市政府 經濟發展局 / 都市發展局 / 環境保護局.
They hold the *authority* (工廠管理輔導法, 區域計畫法) and the *budget*, but lack
continuous monitoring. Their process today is reactive: a citizen reports, an
inspector is dispatched, paperwork (公文) is hand-drafted, and only then can a
cut-off / demolition order proceed.

*Beachhead / channel (moves faster): environmental NGOs already in the workflow*,
namely 地球公民基金會 (Citizens of the Earth Taiwan) and the g0v community behind
*Disfactory* (disfactory.tw). Citizens report suspected factories, and CET files
the paperwork that pressures local governments. They even crowdsource *detection*
through a game, 大家來找廠, where volunteers eyeball aerial imagery to spot new
buildings on farmland. That manual visual change-detection, plus manual paperwork
drafting, is exactly the cognitive labour AgriSentinel automates; we do not invent
demand, we replace a crowdsourcing game and hand-written dossiers with a pipeline,
riding the NGO→government relationship as the cold-start wedge.

*Why us over the status quo.* The status quo is anonymous citizen reports plus a
volunteer game plus manual paperwork: slow, unsystematic, and unscalable across
the ≈50,000 sites. We deliver systematic, island-scalable detection *plus* a
ready-to-file dossier per parcel: the same output an inspector would assemble by
hand, produced in seconds.

= Evidence of Demand and Willingness to Pay

All collection scripts are in `scripts/demand/` and are reproducible.

*1. The problem is real and growing (reproducible).*
`disfactory_stats.py` pulls reported suspected-factory records from the Disfactory
public API around the pilot AOI and buckets them by report year. A representative
run (7 km radius around 和美鎮, retrieved 2026-06) returned *100 reports within
12 km of one township alone*, sustained year after year:

#align(center)[#table(
  columns: 8,
  align: center,
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([*Year*], [2020], [2021], [2022], [2023], [2024], [2025], [2026\*]),
  [Reports near AOI], [6], [14], [28], [14], [21], [10], [7],
)]
Cross-checked against public island-wide figures: ≈50,000 illegal factories on
Taiwan's farmland, 3,000–6,000 new per year, ≈1,500 ha of farmland lost per year
(CET reporting; Disfactory; MOEA statistics; re-verify and cite at submission).
\*2026 partial.

*2. The manual-labour baseline we replace.* The cognitive labour has two halves,
both currently human. (a) *Detection*: the 大家來找廠 volunteer game, ≈1–2 minutes
of careful review per image across tens of thousands of parcels per cycle. (b)
*Dossier drafting*: hand-assembling the 地號, zoning status, evidence, the specific
statute, and a recommended action into filing-ready paperwork. AgriSentinel
automates (a) outright and reduces (b) to *human review of a pre-drafted dossier*.
The survey instrument (`scripts/demand/survey_questions.md`) quantifies both:
time-per-case for staff and minutes-per-image for volunteers (non-monetary WTP).

*3. Published willingness to pay (reproducible).* Government WTP is *public
record*. `tender_search.py` searches the e-procurement portal (政府電子採購網) via
the g0v PCC API for monitoring / remote-sensing / illegal-use keywords. A
representative run returned *370 matching tenders*:

#align(center)[#table(
  columns: 8,
  align: center,
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([*Keyword*], [違章工廠], [農地違規], [航遙測], [遙測影像], [衛星影像], [國土監測], [無人機監測]),
  [Matches], [5], [21], [100†], [100†], [100†], [10], [31],
)]
†page-capped at 100, so true counts are higher. Government bodies already procure
aerial / remote-sensing and land-monitoring services at scale; we attach to an
existing budget line, not a hypothetical one.

*4. Commercial comparable (price anchor).* A Japanese commercial service sells
satellite + AI farmland monitoring to municipalities at ≈¥2,000,000 per
municipality (≈NT\$430,000), claiming ≈80% agreement with physical patrols and
≈3 weeks to deploy, proving the exact pipeline ships commercially.

*5. The defensible claim.* _N_ flagged parcels at precision _P_ (measured against
Disfactory labels, §4); the incumbent is manual crowdsourcing plus hand-written
dossiers; comparable monitoring sells at ≈NT\$430k/municipality; government already
procures remote-sensing monitoring (370+ tenders). At a cost-per-parcel in cents
(§5), the unit economics close at a handful of municipalities.

= System Design

#figure(
  diagram(
    spacing: (8pt, 13pt),
    node-corner-radius: 5pt,
    node-stroke: 0.6pt + rgb("#a9b89e"),
    node-inset: 8pt,
    node((0,0), lyr("SOURCES", [Sentinel-2 L2A (STAC) · Disfactory open API · NLSC land-use / parcels · 全國法規資料庫 statutes]), fill: rgb("#eef1ea")),
    node((0,1), lyr("INGESTION", [`stac_fetch` · `labels_fetch` · `parcels_load` · `laws_fetch` → chunk → embed]), fill: rgb("#e4efe0")),
    node((0,2), lyr("LAKE / STORE", [MinIO (S3): COGs + manifests · PostGIS: parcels, labels, detections, flagged, dossiers · pgvector: law chunks]), fill: rgb("#f5ebda")),
    node((0,3), lyr("PROCESSING", [`change_detect` (NDBI/NDVI) · `spark_tiles` (PySpark) · `zoning_join` (ST_Intersects) · `evaluate` (precision/recall)]), fill: rgb("#e1eeed")),
    node((0,4), lyr("AGENT (value capture)", [`dossier_agent`: pgvector RAG → Claude draft → critic → grounded per-parcel enforcement dossier]), fill: rgb("#d8e7db")),
    node((0,5), lyr("DELIVERY", [FastAPI + Leaflet dashboard · before/after imagery · eval metrics · Kafka worker (new detection → dossiers, SSE)]), fill: rgb("#e6edf5")),
    edge((0,0),(0,1), elbl("fetch"), "-|>"),
    edge((0,1),(0,2), elbl("store"), "-|>"),
    edge((0,2),(0,3), elbl("read AOI tiles"), "-|>"),
    edge((0,3),(0,4), elbl("ranked flagged parcels"), "-|>"),
    edge((0,4),(0,5), elbl("dossiers + metrics"), "-|>"),
  ),
  caption: [End-to-end architecture: sources, ingestion, lake/store, processing, agent, delivery.],
)

#v(4pt)
*Storage and processing: why each tool fits the shape of the data.*

#table(
  columns: (auto, 1fr),
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([*Technology*], [*Justification*]),
  [Sentinel-2 via Planetary Computer STAC], [Free, no-auth, time-series enables change detection; Cloud-Optimized GeoTIFF range reads pull only the AOI footprint (≈0.6 MP/band) of a ≈110 MP scene, keeping volume tractable.],
  [MinIO (S3) + COG], [Raw lake: immutable raster zone, lakehouse pattern; variety plus volume.],
  [PostGIS + pgvector], [One store, two jobs: GIST-indexed spatial joins decide _is this farmland?_ (`ST_Intersects`), and a `vector` column serves the statute RAG (`<=>` cosine).],
  [PySpark (`spark_tiles`)], [Batch paradigm: tiles the AOI and maps change detection per tile; scales to many tiles / historical date pairs by adding executors. Single-process fallback included.],
  [Apache Kafka (KRaft)], [Velocity: a `detection.completed` event fans out to a worker (join→eval→dossiers) and to the dashboard over SSE, so new imagery flows to fresh dossiers with no manual rerun. Any Kafka-API broker (e.g. Redpanda) works.],
  [Anthropic Claude], [The cognitive worker producing the sold artifact (`claude-opus-4-8`; switchable to Sonnet/Haiku for cost at scale).],
  [FastAPI + Leaflet], [Map dashboard, dossier download, before/after imagery, metrics.],
)

*The agent layer (value capture).* `dossier_agent` (1) retrieves the most relevant
statute chunks from pgvector, (2) drafts a *typed, fully-grounded* dossier with
Claude (`messages.parse` → schema), and (3) runs an *adversarial critic* pass that
rejects any claim not traceable to a detection fact or retrieved statute, revising
once. Without an API key it emits a clearly-labelled rule-based template so the
pipeline always completes.

= Implementation and Evaluation

*Change detection.* The default detector is *spectral*: between two dates it flags
pixels where the built-up index rises (ΔNDBI ≥ 0.06) _and_ the vegetation index
falls (ΔNDVI ≥ 0.12), the signature of construction replacing crops, then
vectorises connected regions ≥ 400 m² into candidate polygons with a confidence
score. Requiring *both* signals suppresses the bare-soil / water false positives a
single-index threshold would trip on (verified on a real 0%-cloud Changhua scene:
NDVI ranged −0.21 to 0.62). The interface is swappable: a `torchgeo` Siamese-UNet
(OSCD) path is a documented extension that falls back to spectral with a warning.

*Zoning join: "illegal" = change plus zoning.* A change polygon is only a
_candidate violation_ once it sits on agricultural land. `zoning_join` intersects
detections with farmland parcels in PostGIS, keeps only farmland overlaps, attaches
the 地號, finds the nearest Disfactory label, and ranks by confidence. We never
label a parcel "illegal" without the zoning overlay.

*Evaluation: the credibility anchor.* `evaluate` computes precision / recall of
flagged detections against Disfactory labels within a match radius (default 80 m).
Disfactory labels are crowd-reported and *incomplete*, so these are _indicative,
not absolute_: a flagged parcel with no nearby label may be a real but unreported
factory (precisely the value: surfacing the unreported). A verified offline demo
run (synthetic bi-temporal imagery with injected building patches, deterministic
sample labels) produced:

#align(center)[#table(
  columns: 9,
  align: center,
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([detections], [flagged], [true pos.], [labels], [matched], [*precision*], [*recall*], [*F1*], [radius]),
  [6], [6], [4], [5], [4], [*0.67*], [*0.80*], [*0.73*], [80 m],
)]
The score is deliberately non-trivial (two detected patches have no label, so two
false positives; one labelled factory has no detectable patch, so one miss), and
the demo reports an honest figure rather than a staged 100%. The same metric is
shown live on the dashboard for any run; the live pipeline runs the identical
stages on a real Sentinel-2 pair for the AOI.

= Scalability and Cost (10× / 100×)

#table(
  columns: (auto, 1fr, 1fr, 1fr),
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([*Concern*], [*Pilot (1 township)*], [*10× (1 county)*], [*100× (national)*]),
  [Imagery], [windowed COG reads, MinIO], [partition by tile/date], [real S3; Sentinel-1 SAR fusion to beat cloud],
  [Compute], [single-proc / local Spark], [Spark, few executors], [Spark cluster; CD is embarrassingly parallel],
  [Store], [one PostGIS], [partition by AOI; read replicas], [sharded PostGIS + parquet for cold detections],
  [Agent], [per-parcel Claude calls], [prompt-cache statutes; Batch API], [Batch + Haiku triage / Opus confirm; cents/parcel],
  [Stream], [one Kafka broker], [partitions per county], [multi-broker; consumer groups per region],
)
*Unit economics.* A dossier is a few thousand tokens of context plus output, about
a few US cents per parcel, versus monitoring contracts in the hundreds of thousands
of NT\$ and volunteer-hours per detection. The compounding moat is the *imagery
archive*: every cycle of snapshots is history a later competitor cannot reproduce.

= Go-to-Market Difficulties (bonus)

- *Trust / adoption.* Answer with the precision / recall against known factories, a
  per-flag confidence score, and a *human-in-the-loop review* before any dossier is
  filed. The product is decision-support, never an automated ruling.
- *Data acquisition cost and licensing.* Sentinel-2 and Disfactory are open
  (CC BY 4.0 cited); statutes are MOJ open data. The real friction is the *NLSC
  vector cadastre* (地籍 WFS), which requires a government / academic application, so
  the demo ships a deterministic synthetic parcel layer (labelled
  `source='synthetic'`) and the production path joins the official farmland layer
  once access is granted. That gating becomes a moat once we are inside the channel.
- *Legal / ethics / PDPA.* The dossier targets parcels / structures, not persons;
  no private individuals are named; cautious "suspected / candidate" language.
- *Don't antagonise the incumbent.* We augment CET / Disfactory's proven workflow
  and the government's authority: leverage, not replacement.
- *Cold start.* Beachhead through the NGO channel; one county pilot before island
  scale; the eval number is the trust-builder that unlocks the first paid pilot.
- *Competition and moat.* A scraper of Disfactory is worthless (the data is free);
  the moat is the fused per-parcel substrate, the inspector-judgment scaffolding
  encoded in the detection→zoning→dossier pipeline, the compounding archive, and
  distribution inside the enforcement channel.

= Caveats and Honesty

*Cloud cover.* Taiwan is cloudy; mitigated with low-cloud scene selection and
multi-temporal windows; SAR fusion is a noted scale TODO. *Resolution.* 10 m is
coarse for small buildings, used as a "something changed" trigger to be confirmed
with higher-res orthophotos. *Eval honesty.* Disfactory labels are incomplete, so
precision / recall are indicative; the synthetic parcel / imagery fallback is for
offline reproducibility and is always labelled as such, never presented as real.

= Reproducibility and Deliverables

One-command run: `make demo` (live) or `make demo-offline` (offline). Demand
evidence: `scripts/demand/*` regenerate §2's numbers. Tests: `make test`
(unit plus DB-integration, including zoning-join correctness). The repository
contains all ingestion / processing / agent / delivery code, a runnable
`README.md`, and an architecture overview mirroring §3.

#table(
  columns: (auto, auto, 1fr),
  inset: 5pt,
  stroke: 0.4pt + rgb("#d9d6c8"),
  table.header([*Criterion*], [*Weight*], [*Where*]),
  [Target customer clarity], [20%], [§1],
  [Demand evidence and acquisition], [25%], [§2 + `scripts/demand/`],
  [Technical system and implementation], [40%], [§3–§5 + the repository],
  [Writing, diagrams, presentation], [15%], [this report + the §3 diagram + dashboard],
  [Bonus: GTM difficulties], [+10%], [§6],
  [Bonus: live deployment], [+10%], [live URL on page 1 (optional)],
)
