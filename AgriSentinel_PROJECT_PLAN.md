# AgriSentinel — Project Plan

**Automated detection of illegal factories on farmland + AI-generated enforcement dossiers.**

> Big Data Systems final project (Spring 2026, NTU). This document is the single source of truth for implementation. It is written to be handed to Claude Code as a build spec; it can also seed a `CLAUDE.md`/`PLAN.md` at the repo root. It carries both the *technical build* and the *business/context argument* the written report must make.

---

## 0. How to use this document (instructions for the build agent)

- **Goal is a thin, working, end-to-end slice over one pilot region — not a production system.** The course explicitly rewards "the smallest end-to-end pipeline that delivers value, even if it only handles a tiny slice of data." Optimize for *demonstrably working* over *complete*.
- **Pin the pilot region** to Changhua County (彰化縣) — the canonical hotspot for illegal farmland factories. Pick one township bounding box (e.g., 和美鎮 / 鹿港鎮 area) so imagery volume stays tractable.
- Build in the **phase order** in §6. Each phase has acceptance criteria; do not advance until they pass.
- Prefer **free, no-auth-friction data sources** (Microsoft Planetary Computer STAC for Sentinel-2; Disfactory open data/API for labels). Keep secrets in `.env`.
- Everything runs via **`docker compose up`** locally. Keep the README runnable by a grader who has only Docker + an Anthropic API key.
- When a design decision is ambiguous, choose the option that makes the demo work for the pilot region this week, and leave a `# TODO(scale)` note for the 10×/100× discussion.

---

## 1. Context & thesis (this is the argument the report must defend)

Raw, public, easy data has no durable value — in competition, price falls to the marginal cost of production, and a 200-line scraper has a marginal cost near zero. The durable value is in **cognitive labor**: the work a human analyst/inspector does to turn messy inputs into a decision-grade artifact. As of 2026, AI agents perform that cognitive labor at a fraction of the human wage. The product we sell is the **agent's output artifact**, not the data underneath. The big-data pipeline exists to feed the agent a substrate so fresh and well-structured that its output beats anything the customer could get from a generic chatbot — that is what makes the data engineering load-bearing rather than decorative.

**The customer asymmetry this project exploits:** government has *authority* but no *eyes*. It can lawfully cut water/electricity and demolish illegal structures, but it does not continuously watch the farmland. It learns about violations late, after they crystallize into pollution or scandal. The technical edge is **collapsing the observation lag** — giving the enforcement authority real-time sight of new encroachment. There is no luck here (the opposite of finance/alpha-farming): either the pipeline sees the new structure or it doesn't. The edge is purely technical capability.

**The human-labor baseline already exists and is manual.** The NGO 地球公民基金會 (Citizens of the Earth Taiwan) + the g0v community run **Disfactory** (disfactory.tw): citizens report suspected illegal factories, and the NGO files the paperwork that pressures local governments to act. They even crowdsource the detection through a game, **大家來找廠**, where volunteers eyeball aerial imagery to spot new buildings on farmland. That manual visual change-detection, plus the manual drafting of enforcement paperwork (公文), is exactly the cognitive labor AgriSentinel automates. We are not inventing demand; we are replacing a crowdsourcing game and hand-written dossiers with a pipeline.

**Scale of the problem (for the report's demand section):**
- ~50,000 illegal factories on Taiwan's farmland; 3,000–6,000 new ones per year.
- ~1,500 hectares of farmland lost to illegal use per year.
- Enforcement endpoint is real: water/electricity cutoff and demolition.

**Willingness-to-pay benchmark:** a Japanese commercial service sells satellite + AI farmland monitoring to municipalities at roughly ¥2,000,000 per municipality (~NT$430k), claiming ~80% agreement with physical patrols and ~3 weeks to deploy. This is the price comparable and a proof that the exact pipeline ships commercially.

> All figures above are sourced from public reporting and the Disfactory project; re-verify and cite at report-writing time. Reproducibility scripts for the demand evidence live in `scripts/demand/` (see §7).

---

## 2. Customer, product, and moat (Report Components 1 & 3)

**Target customer (Component 1).**
- *Primary (the whale):* county/municipal enforcement units — 縣市政府 經濟發展局 / 都市發展局 / 環境保護局 — responsible for farmland-factory enforcement. They have authority + budget but lack continuous monitoring.
- *Beachhead / channel (moves faster):* environmental NGOs already in this workflow (CET/Disfactory). They are the existing "eyes" and have the government relationships; augmenting them is the cold-start wedge.
- *Why us over the status quo:* the status quo is anonymous citizen reports + a volunteer crowdsourcing game + manual paperwork. We deliver systematic, island-scalable detection + a ready-to-file enforcement dossier.

**Product (the artifact sold).** A per-parcel **enforcement dossier**: detected new structure, parcel land number (地號), zoning status, before/after imagery, the specific statute violated, confidence score, and a recommended action — plus a monitoring dashboard. The dossier is decision-support, not a legal determination.

**Moat.**
1. *Substrate* — fused multi-temporal imagery + zoning/cadastral overlay nobody assembles per-parcel at scale.
2. *Scaffolding* — the detection→zoning-join→dossier pipeline encodes the inspector's judgment.
3. *Compounding archive* — every cycle of snapshots is history a later competitor cannot reproduce.
4. *Distribution* — sitting inside the NGO→government enforcement channel.

---

## 3. System architecture

```
            SOURCES                         INGESTION                       LAKE / STORE
 ┌──────────────────────────┐     ┌───────────────────────────┐    ┌────────────────────────┐
 │ Sentinel-2 L2A (STAC,    │────▶│ stac_fetch  (bi-temporal  │───▶│ MinIO (S3): raw tiles, │
 │  Planetary Computer)     │     │  scene pairs for AOI)     │    │  COGs, parquet         │
 │ NLSC orthophotos (WMTS)  │────▶│ ortho_fetch               │    │                        │
 │ Disfactory open data/API │────▶│ labels_fetch (known       │───▶│ PostGIS: parcels,      │
 │ NLSC farmland/zoning +   │────▶│  factories = eval labels) │    │  zoning, detections,   │
 │  cadastral (地號) layer  │     │ parcels_load              │    │  dossiers              │
 │ Laws (全國法規資料庫)    │────▶│ laws_fetch → chunk → embed│───▶│ pgvector: regulation   │
 └──────────────────────────┘     └─────────────┬─────────────┘    │  chunks                │
                                                 │                  └────────────────────────┘
                                                 ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │ PROCESSING                                                                    │
   │  change_detect (torchgeo / pretrained Siamese-UNet on S2 pairs)  ── batch ──▶ │  PySpark job tiles
   │  zoning_join   (spatial join detections × farmland parcels, PostGIS)          │  the AOI & runs CD
   │  evaluate      (precision/recall vs Disfactory labels)                        │  per tile
   └───────────────────────────────────┬───────────────────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │ AGENT LAYER  (the value-capture worker)                           │
   │  dossier_agent: retrieves matching statute chunks (pgvector RAG) + │
   │  structured detection facts → Claude drafts enforcement dossier    │
   │  (地號, zoning, before/after, violated law, action, confidence)    │
   └───────────────────────────────────┬──────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │ DELIVERY                                                          │
   │  FastAPI  +  Leaflet map dashboard: flagged parcels, imagery,     │
   │  downloadable dossiers, eval metrics. Redpanda/Kafka event:       │
   │  "new imagery → detection → new dossier" stream to dashboard.     │
   └──────────────────────────────────────────────────────────────────┘
```

---

## 4. Tech stack (and why each earns its place in a *Big Data Systems* project)

| Layer | Choice | Justification tied to data property |
|---|---|---|
| Imagery source | Sentinel-2 L2A via **Microsoft Planetary Computer STAC**; **NLSC orthophoto WMTS** for high-res confirmation | Free, no-auth STAC search; time-series enables change detection |
| Message/stream | **Redpanda** (Kafka API-compatible, light) | Velocity: new-imagery/new-detection events fan out to consumers |
| Raw lake | **MinIO** (S3-compatible) + Cloud-Optimized GeoTIFF + parquet | Variety + volume: raster tiles, immutable raw zone, lakehouse pattern |
| Batch | **PySpark** job to tile the AOI and run change detection per tile | Batch paradigm: reprocess many tiles / historical dates |
| Spatial store | **PostGIS** | Parcels, zoning, detections, spatial joins |
| Vector store | **pgvector** (in the same Postgres) | Semantic retrieval of regulation chunks for the dossier RAG |
| CV model | **torchgeo** + pretrained change-detection (Siamese U-Net; OSCD weights) / `segmentation-models-pytorch` | Reuse, don't reinvent; OSCD is Sentinel-2-native |
| Agent | **Anthropic API** (`claude-...`), orchestrated with a small planner→retrieve→draft→critique loop | The cognitive worker producing the sold artifact |
| Delivery | **FastAPI** + **Leaflet** (static or minimal React) | Map dashboard + dossier download + metrics |
| Orchestration | **docker compose**; `Makefile` targets; optional **Prefect** for the pipeline DAG | One-command local run for graders |
| Deploy (bonus) | **Fly.io** or **Render** via the same compose images | Live demo URL on PDF page 1 |

> If GPU is unavailable, run change detection on CPU over a small AOI, or use thresholded spectral-index differencing (e.g., NDBI/NDVI deltas) as a fallback detector. Keep the model interface swappable.

---

## 5. Repository layout

```
agrisentinel/
├── README.md                      # one-command run + architecture overview (mirror §3)
├── CLAUDE.md                      # condensed build rules from §0 of this plan
├── docker-compose.yml             # minio, postgis(+pgvector), redpanda, api
├── Makefile                       # make ingest / detect / serve / eval / demo
├── .env.example                   # ANTHROPIC_API_KEY, PC_SUBSCRIPTION_KEY?, DB_URL, S3_*
├── config/
│   └── aoi_changhua.yaml          # pilot bounding box, date pairs, thresholds
├── ingestion/
│   ├── stac_fetch.py              # Sentinel-2 bi-temporal pairs (Planetary Computer)
│   ├── ortho_fetch.py             # NLSC WMTS orthophoto tiles
│   ├── labels_fetch.py            # Disfactory open data/API → known factories (eval set)
│   ├── parcels_load.py            # farmland parcels + 地號 + zoning → PostGIS
│   └── laws_fetch.py              # statutes → chunk → embed → pgvector
├── processing/
│   ├── change_detect.py           # torchgeo model inference over tiles
│   ├── spark_tiles.py             # PySpark: tile AOI, map change_detect per tile
│   ├── zoning_join.py             # detections × farmland parcels (PostGIS)
│   └── evaluate.py                # precision/recall vs Disfactory labels
├── agent/
│   ├── dossier_agent.py           # RAG + Claude → enforcement dossier (md/JSON/PDF)
│   └── prompts/                   # planner / drafter / critic prompts
├── api/
│   ├── main.py                    # FastAPI: parcels, detections, dossiers, metrics
│   └── stream.py                  # Redpanda consumer → push new detections
├── dashboard/
│   └── index.html                # Leaflet map + dossier viewer + metrics panel
├── scripts/
│   └── demand/                    # reproducible demand-evidence collection (§7)
│       ├── disfactory_stats.py    # pull factory counts / time trend
│       ├── tender_search.py       # 政府電子採購網 keyword search → CSV
│       └── survey_questions.md    # the exact survey instrument
├── report/
│   └── report.md                  # the PDF report source (build with the docx/pdf flow)
└── tests/
    └── ...                        # at least: ingestion smoke, zoning-join correctness
```

---

## 6. Implementation phases (build in this order; each gates the next)

### Phase 0 — Scaffolding & infra
- Create repo layout (§5), `docker-compose.yml` (MinIO, PostGIS+pgvector, Redpanda, API), `.env.example`, `Makefile`, `config/aoi_changhua.yaml`.
- **Acceptance:** `docker compose up` brings all services healthy; `make` targets stubbed; README explains run steps.

### Phase 1 — Ingestion
- `stac_fetch.py`: pull a bi-temporal Sentinel-2 L2A pair (two dates, low cloud) for the pilot AOI from Planetary Computer; store COGs in MinIO.
- `parcels_load.py`: load farmland parcels + zoning + 地號 into PostGIS for the AOI.
- `labels_fetch.py`: pull Disfactory known-factory points for the AOI as the evaluation label set.
- `ortho_fetch.py` (optional this phase): NLSC orthophoto tiles for high-res confirmation.
- **Acceptance:** AOI imagery in MinIO; parcels + labels queryable in PostGIS; a notebook/script renders one parcel with its imagery.

### Phase 2 — Change detection
- `change_detect.py`: load a pretrained Sentinel-2 change-detection model (torchgeo/OSCD) or the NDBI/NDVI-delta fallback; output candidate change polygons for the AOI pair.
- `spark_tiles.py`: PySpark job that tiles the AOI and runs `change_detect` per tile, writing change polygons to PostGIS.
- **Acceptance:** change polygons for the AOI persisted; visual spot-check shows plausible new-construction hits.

### Phase 3 — Zoning join, filter, evaluate
- `zoning_join.py`: spatial-join change polygons against farmland parcels; keep only new structures on agricultural land; attach 地號 + zoning.
- `evaluate.py`: compute precision/recall of flagged parcels against Disfactory labels; write a metrics JSON.
- **Acceptance:** a ranked list of flagged farmland parcels with a reported precision/recall number against known factories. **This metric is the technical credibility anchor — do not skip.**

### Phase 4 — Agent dossier generation
- `laws_fetch.py`: ingest the relevant statutes (工廠管理輔導法, 區域計畫法 / 非都市土地使用管制規則, 農業發展條例) from 全國法規資料庫; chunk + embed into pgvector.
- `dossier_agent.py`: for each flagged parcel, retrieve matching statute chunks + structured facts (地號, zoning, before/after, confidence) and have Claude draft the enforcement dossier (markdown + JSON; optional PDF). Use a small planner→draft→critic loop; every factual claim must trace to a retrieved fact or statute chunk.
- **Acceptance:** for ≥5 flagged parcels, a generated dossier that names the parcel, the violated statute, the evidence, and a recommended action, with no fabricated facts.

### Phase 5 — Delivery
- `api/main.py`: FastAPI endpoints for parcels, detections, dossiers, metrics.
- `dashboard/index.html`: Leaflet map of flagged parcels; click → before/after imagery + dossier + confidence; a metrics panel.
- **Acceptance:** a grader opens the dashboard, clicks a flagged parcel, sees imagery + dossier.

### Phase 6 — Stream wiring (course requirement)
- `api/stream.py` + Redpanda: emit a "new detection" event from Phase 3; consumer pushes it to the dashboard / triggers dossier generation.
- **Acceptance:** dropping a new imagery date triggers detection → event → dossier → dashboard update without a manual rerun.

### Phase 7 — Demand evidence, report, deploy (bonus)
- Run `scripts/demand/*` (§7); write `report/report.md`; build the PDF (put GitHub + live URLs on page 1).
- Deploy via compose images to Fly.io/Render for the live-demo bonus.
- **Acceptance:** PDF + repo + (optional) live URL all consistent; demand section cites reproducible numbers.

---

## 7. Demand evidence plan (Report Component 2 — 25%, the heaviest)

Document the *process*, not just the conclusion. Scripts live in `scripts/demand/`.

1. **Quantify the problem** (`disfactory_stats.py`): pull Disfactory open data for factory counts and the new-per-year trend; chart it. Cross-check against the ~50k / 3–6k-per-year / 1,500 ha-per-year public figures.
2. **Quantify the manual-labor baseline:** describe the 大家來找廠 crowdsourcing game and CET's manual paperwork as the human cognitive labor being replaced; estimate volunteer-hours per detection.
3. **Published willingness-to-pay** (`tender_search.py`): keyword-search 政府電子採購網 for monitoring/顧問/航遙測/違章 tenders; export matches + award amounts to CSV. Government WTP is *public record* — exploit it.
4. **Commercial comparable:** the Japanese municipality service at ~¥2M/municipality, ~80% patrol agreement, ~3-week deploy.
5. **Primary signal (optional but strong):** a short survey/interview of local-government enforcement staff and/or CET volunteers (instrument in `survey_questions.md`).
6. **Defensible claim to build toward:** "N flagged parcels at precision P; the incumbent process is manual crowdsourcing + hand-written dossiers; comparable monitoring sells at ~NT$430k/municipality; at our cost-per-parcel of NT$X the unit economics close at K municipalities."

---

## 8. Go-to-market difficulties (Report Component 3 — bonus +10%)

- **Trust/adoption:** why trust automated detection? Answer with the Phase-3 precision/recall against known factories, and keep a human-in-the-loop review step before any dossier is "filed."
- **Data/licensing:** Sentinel-2 and Disfactory data are open (cite licenses, CC BY 4.0 for Disfactory contributions); respect NLSC terms and robots.txt for any crawling.
- **Legal/ethics:** the dossier is *decision-support*, not a legal ruling; avoid naming private individuals; the artifact targets parcels/structures, not persons. PDPA-aware.
- **Don't antagonize the incumbent:** you augment CET/Disfactory's proven workflow and the government's authority — frame as leverage, not replacement.
- **Cold start:** beachhead through the NGO channel; one county pilot before island scale.
- **Unit economics & moat:** cost-per-parcel in cents vs. monitoring contracts in hundreds of thousands; the compounding imagery archive is the durable moat.

---

## 9. Known caveats / scope guards (read before building)

- **Cloud cover:** Taiwan is cloudy; optical Sentinel-2 has gaps. Mitigate with multi-temporal compositing, low-cloud scene selection, or NLSC orthophotos for confirmation. Commercial systems fuse optical + SAR (Sentinel-1) — note as a `# TODO(scale)`, don't block the MVP on it.
- **Resolution:** 10 m Sentinel-2 is coarse for small buildings — use it for "something changed," confirm with higher-res NLSC orthophotos. Keep the detector interface swappable.
- **"Illegal" = change + zoning:** a new structure is only a candidate violation once the zoning join confirms agricultural land. Never label a parcel "illegal" without the zoning overlay.
- **Eval honesty:** Disfactory labels are incomplete (crowd-reported), so treat precision/recall as indicative, not absolute; say so in the report.

---

## 10. Deliverables checklist (from the course spec)

- [ ] PDF report (English, single file); **GitHub URL on page 1**; (bonus) **live URL on page 1**.
- [ ] GitHub repo: all ingestion/processing/delivery code, runnable `README.md`, `scripts/demand/` reproducibility, short architecture overview mirroring §3.
- [ ] Clean architecture diagram in the PDF (redraw §3).
- [ ] (Bonus) Working dashboard a grader can open in a browser.
- [ ] (Bonus) GTM section (§8) and 10×/100× scale-and-cost sketch.

## 11. Rubric map

| Criterion | Weight | Covered by |
|---|---|---|
| Target customer clarity | 20% | §2 (enforcement units + NGO channel) |
| Demand evidence & acquisition | 25% | §7 (Disfactory stats, tenders, comparable, survey) |
| Technical system & implementation | 40% | §3–§6 (multi-source raster pipeline, Spark, stream, PostGIS, agent) |
| Writing, diagrams, presentation | 15% | §3 diagram, `report/report.md`, eval metrics |
| Bonus: GTM difficulties | +10% | §8 |
| Bonus: live deployment | +10% | Phase 7 |

---

## 12. First commands for the build agent

1. Scaffold the repo per §5 and bring up `docker compose` (Phase 0).
2. Implement Phase 1 ingestion for the Changhua AOI; verify imagery + parcels + labels land in MinIO/PostGIS.
3. Stop at each phase's acceptance criteria and report status before proceeding.

*End of plan.*
