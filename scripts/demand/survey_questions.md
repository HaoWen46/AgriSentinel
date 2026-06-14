# AgriSentinel — Demand Survey Instrument (Component 2)

The exact questions used to gather primary willingness-to-pay / time-saved
evidence. Two short instruments target the two customer groups in §2 of the
plan: (A) county/municipal enforcement staff (the whale), and (B) CET / g0v
Disfactory volunteers (the beachhead channel). Keep it under 10 minutes.

**Consent note (read first):** Responses are used only in aggregate for this
academic project. No personally identifying information is collected. You may
skip any question.

---

## Instrument A — County/Municipal enforcement staff (經發局 / 都發局 / 環保局)

**Background**
1. Which unit do you work in, and what is your role in farmland-factory
   enforcement?
2. Roughly how many new suspected illegal-factory cases does your unit handle
   per month?

**Current process (the status quo we replace)**
3. How do you currently *learn* about a new structure on farmland? (citizen
   report / Disfactory / patrol / aerial photo review / other)
4. From "a structure appears" to "your unit knows about it", what is the typical
   lag? (days / weeks / months)
5. Walk through what happens after you receive a report: which steps, which
   systems, how long does preparing the enforcement paperwork (公文) take per
   case? (estimate in person-hours)
6. What is the hardest or most time-consuming part of that process?

**The product**
7. If you received a ready-to-review dossier per parcel — detected new structure,
   地號, zoning status, before/after imagery, the specific statute, a confidence
   score, and a recommended action — how would that change your workflow?
8. What would make you *trust* an automated detection enough to act on it?
9. What is a dealbreaker that would stop you from adopting such a tool?

**Willingness to pay**
10. Does your unit currently pay for any monitoring / aerial-survey / 顧問
    service related to this? If so, roughly how much per year?
11. For island-scalable monitoring + dossier generation, what annual budget
    range is realistic for your unit? (free-text or: <NT$100k / 100–300k /
    300–500k / >500k)
12. Would you prefer per-municipality subscription, per-case pricing, or a
    bundle with the existing patrol budget?

---

## Instrument B — CET / Disfactory volunteers (beachhead channel)

1. How long have you contributed to Disfactory / 大家來找廠?
2. On average, how many minutes does it take you to review one aerial image and
   decide whether there is a new building?
3. How many images do you typically review in one session?
4. What fraction of images, in your experience, contain a genuine new structure?
5. What is most tedious or error-prone about the manual review game?
6. If a pipeline pre-flagged likely new structures (with before/after chips) and
   you only *verified* them, how much time would that save you per case?
7. Would a pre-drafted enforcement dossier (for the NGO to file) be useful, or
   does the manual drafting add value you would not want automated?
8. What would make you distrust an automated flag?

---

## How responses feed the report

- Q4/Q5 (A) and Q2/Q6 (B) quantify the **manual cognitive labour** AgriSentinel
  automates → time-saved estimate (non-monetary WTP).
- Q10/Q11 (A) give **monetary WTP**, triangulated with the public tender records
  (`tender_search.py`) and the commercial comparable (~NT$430k/municipality).
- Q8/Q9 (A) and Q8 (B) feed the **trust / go-to-market difficulties** section
  (Component 3).
