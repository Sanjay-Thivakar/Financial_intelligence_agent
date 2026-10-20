# Phase 5E — News Data Source, Licensing & Coverage Audit Report

**Date:** 2026-10-16  
**Status:** Audit Complete — Conditional Go / Staged Text Architecture Defined  
**Governing Modules & Files Inspected:**  
- `docs/phase2_fnspid_report.md` (Initial FNSPID exploration & rejection)  
- `docs/phase3a_data_source_research.md` (Primary data source research)  
- `docs/phase4b_news_pipeline_report.md` (News ingestion schema & baseline features)  
- `docs/phase4c_unified_dataset_report.md` (Multi-modal alignment & leakage checks)  
- `docs/phase5_training_dataset_readiness_report.md` (Training data readiness & authorization)  
- `src/data/market/storage_policy.py` (`StoragePolicy` rules & license status matrix)  
- `src/data/news/schema.py` (`PROCESSED_NEWS_SCHEMA`, deterministic `news_id`)  
- `src/data/news/ingestor.py` (`NewsIngestor`, interval-aware company mapping)  
- `src/features/news.py` (`NewsFeatureEngine`, point-in-time eligibility)  
- `data/processed/news/fnspid_news_processed.parquet` (Local processed news sample: 8,830 rows)  
- `data/processed/news/fnspid_news_processed_validation_report.json` (Automated data quality validation report)  
- `data/raw/sec/submissions/` (Local SEC submissions: CIK 0000320193, 0000019617, 0000789019, 0000816284, 0001326801)  

---

## 1. Executive Decision: CONDITIONAL GO (STAGED ARCHITECTURAL PIVOT)

We issue a **CONDITIONAL GO with a mandatory architectural pivot** for news and textual event integration:

1. **NO-GO for FNSPID as a Primary Training Source**:
   - **Empirical Blocker**: In our 4-company Phase 5C evaluation cohort (`AAPL`, `JPM`, `GOOG`, `TSLA`), FNSPID contains records **only for AAPL** (441 records). Coverage for `JPM`, `GOOG`, and `TSLA` is **0.0% (0 records)**.
   - **Text Quality Defect**: 100.0% of records in the processed sample are **headline-only** (`article_text` length = 0).
   - **Legal Defect**: The underlying text consists of scraped third-party commercial news (Reuters, Bloomberg, Benzinga, Nasdaq) without documented publisher redistribution consent.
   - **Role**: FNSPID is strictly restricted to offline, auxiliary pipeline ablation tests. It **must not** be used as an authorized primary training source.
2. **NO-GO for Free-Tier Commercial Aggregators (Finnhub & Tiingo) for Historical Backtesting**:
   - **Finnhub Free Tier**: Hard-capped to a **maximum of 1 year** of historical news. This completely blocks backtesting our 2019–2020 benchmark window.
   - **Tiingo Starter Tier**: Queryable news history on standard tiers is restricted to recent months (~3 months); deep 15-year historical backfills require paid commercial/institutional agreements. Both providers restrict free-tier data to personal internal use and prohibit bulk database warehousing.
3. **CONDITIONAL GO for SEC Form 8-K Disclosures as the Unencumbered Primary Event Layer**:
   - **Legal Authorization & Reuse Policy**: 
     - *Statutory Distinction*: 17 U.S.C. § 105 applies strictly to works created by officers or employees of the US Government. Corporate filings and exhibits (including Exhibit 99.1 press releases) are authored by private filers and corporations, not government employees.
     - *SEC Dissemination Policy*: The SEC's official Webmaster FAQ ([https://www.sec.gov/about/webmaster-frequently-asked-questions](https://www.sec.gov/about/webmaster-frequently-asked-questions)) establishes that SEC.gov and EDGAR public filing content are *"free to access and reuse without special permission"*.
     - *Classification*: Structured filing metadata (Item numbers, filing dates, accession numbers) and local research caching for derived statistical features are **VERIFIED_ALLOWED**. However, commercial model training on full-text corporate-authored exhibits or commercial redistribution of raw corporate press releases remains **RESTRICTED / UNVERIFIED** under evolving copyright boundaries.
   - **Historical Depth**: Electronic EDGAR filing was phased in between 1993 and 1996; the modern 8-K item taxonomy was enacted in August 2004 (Release No. 33-8400); and coverage varies based on individual company registration/IPO dates (e.g. GOOG in 2004, TSLA in 2010). Coverage cannot be assumed universal from 1994.
   - **Point-in-Time Availability**: `acceptanceDateTime` records when EDGAR's intake subsystem successfully validated the filing. The SEC documents that public website and API availability typically follows acceptance by a **1 to 3 minute dissemination lag** (with no guaranteed upper bound during server spikes). A conservative backtesting availability rule must enforce an availability buffer ($\ge 5$ minutes post-acceptance). "Zero lookahead leakage" cannot be claimed without this qualification.
   - **Entity Resolution**: Authoritative entity linkage via canonical SEC CIK (`company_id`).
   - **Text Completeness**: Full-text corporate disclosures and attached press releases (Exhibit 99.1).
4. **Implementation Condition**:
   - No sentiment model or news prediction model may be trained until uniform, multi-company event coverage is empirically verified across all cohort companies.

---

## 2. Scope and Methodology

This audit evaluates the viability of candidate news and textual event sources across eight rigorous criteria:
1. **Licensing & Legal Status**: Explicit terms of service, publisher copyright, commercial model training, local disk persistence, and redistribution rights.
2. **Temporal Depth & Backtest Availability**: Coverage of historical benchmark periods (specifically 2019–2020) and free-tier access barriers.
3. **Point-in-Time Precision & Availability Boundaries**: Second-level vs day-level timestamps, timezone semantics, and avoidance of lookahead leakage.
4. **Text Content Fidelity**: Headlines vs summaries vs full article bodies.
5. **Entity Resolution & Ticker Succession**: Immunity to ticker recycling, acquisitions, and symbol changes.
6. **Cohort Coverage in the Active Prototype**: Representation across the 4 verified Phase 5C companies (`AAPL`, `JPM`, `GOOG`, `TSLA`) and resolution of `AA`.
7. **Storage Policy Conformance**: Alignment with `StoragePolicy` (`src/data/market/storage_policy.py`).
8. **Operational Sustainability & Cost**: Compliance with fair-access rate limits without recurring commercial subscriptions.

---

## 3. Existing FNSPID Audit & Empirical Limitations

We performed an audit of the local FNSPID dataset [`data/processed/news/fnspid_news_processed.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/news/fnspid_news_processed.parquet) and the raw source [`data/raw/news/fnspid_all_external_sample.csv`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/raw/news/fnspid_all_external_sample.csv).

### 3.1 Dataset Inventory & Statistics
- **Total Records**: 8,830 rows $\times$ 11 columns.
- **Date Range**: 2009-04-29 to 2020-06-10 (abrupt cutoff in June 2020).
- **Text Body Completeness**: **0.0%**. Exactly 8,830 of 8,830 records (100.0%) have an empty `article_text` field (`empty_article_text_pct = 100.0%`).
- **Timestamp Precision**: 100.0% of records have parsed intraday timestamps (`has_intraday_time = True`), but the source format reflects scraped web timestamps with variable reporting latency.
- **Universe Matching Rate**: Only 3,620 of 8,830 records (41.0%) map to active S&P 500 company intervals. 5,210 records (59.0%) have `company_id = NaN`.

### 3.2 Ticker & Company Breakdown in Local FNSPID Sample

| Ticker | Canonical Company ID | S&P 500 Company Name | Record Count | Date Range in Sample | Usable Status in Phase 5C Panel |
| :---: | :---: | :--- | :---: | :---: | :--- |
| **AAPL** | `US_CIK_0000320193` | Apple Inc. | 441 | 2020-03-09 $\to$ 2020-06-10 | **Present** (66 trading days overlap; headlines only) |
| **A** | `US_CIK_0001090872` | Agilent Technologies | 1,417 | 2009-04-29 $\to$ 2020-06-10 | Not in Phase 5C market cohort |
| **AAP** | `US_CIK_0001158449` | Advance Auto Parts | 817 | 2011-03-07 $\to$ 2020-06-10 | Not in Phase 5C market cohort |
| **AAL** | `US_CIK_0000006201` | American Airlines Group | 460 | 2013-12-09 $\to$ 2020-06-10 | Not in Phase 5C market cohort |
| **ABBV** | `US_CIK_0001551152` | AbbVie Inc. | 485 | 2013-01-02 $\to$ 2020-06-10 | Not in Phase 5C market cohort |
| **AA** | `NaN` (Unresolved) | *Alcoa / Arconic (Ambiguous)* | 2,697 | 2009-04-29 $\to$ 2020-06-10 | **EXCLUDED** (Entity unmapped; corporate split ambiguity) |
| **16 Other Tickers** | `NaN` (Unmapped) | Non-S&P 500 entities (AAC, AAN, AAOI, etc.) | 2,513 | 2009-04-29 $\to$ 2020-06-10 | **EXCLUDED** (Outside canonical S&P 500 universe) |
| **JPM** | `US_CIK_0000019617` | JPMorgan Chase | **0** | N/A | **COMPLETELY MISSING (0 records)** |
| **GOOG** | `US_CIK_0001652044` | Alphabet Inc. | **0** | N/A | **COMPLETELY MISSING (0 records)** |
| **TSLA** | `US_CIK_0001318605` | Tesla, Inc. | **0** | N/A | **COMPLETELY MISSING (0 records)** |

### 3.3 Critical Impact on Phase 5 Comparative Evaluations
If FNSPID news features are joined into the 4-company panel (`AAPL`, `JPM`, `GOOG`, `TSLA`), **75% of the panel rows would have completely missing news features**. Evaluating a "market + fundamentals + news" model on this sample would not measure the predictive power of news; it would merely measure an idiosyncratic Apple-specific dummy feature against three uninformative zero/median imputed series.

---

## 4. Candidate-Source Comparison Table

We evaluated five candidate news and event sources against the project's requirements:

| Dimension | SEC Form 8-K & Exhibits | Tiingo Financial News | Finnhub Company News | FNSPID Dataset | MarketAux API |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Data Category** | Material Corporate Announcements & Press Releases | Aggregated Commercial News & Summaries | Real-Time Company News & Market Feeds | Historical Academic News Corpus | Global Multilingual Financial News |
| **Legal Classification** | **VERIFIED_ALLOWED (Metadata & Facts)** / **RESTRICTED (Full-Text AI/Redistribution)** | **RESTRICTED** | **NOT_ALLOWED (Free Hist)** | **UNVERIFIED** | **RESTRICTED** |
| **Licensing Framework** | SEC Dissemination Policy (Webmaster FAQ); 17 U.S.C. § 105 (Govt Works only) | Proprietary Commercial ToS (Starter / Power) | Proprietary Commercial ToS (Free Personal) | CC-BY Paper / Scraped Publisher Media | Proprietary SaaS ToS (Free / Paid) |
| **Local Disk Storage** | **PERMITTED** (Raw JSON & Normalized Parquet) | **PROHIBITED** (Starter) / Restricted (Power) | **PROHIBITED** (Free Tier Personal Use) | **UNVERIFIED / PROHIBITED** (Publisher Copyright) | **PROHIBITED** (Free Tier) |
| **Commercial Model Training** | **UNVERIFIED (Corporate Full Text)** / **PERMITTED (Statistical Features)** | Enterprise Agreement Required | Enterprise Agreement Required ($500+/mo) | **UNVERIFIED** (Tainted Provenance) | Commercial License Required |
| **Historical Depth** | Electronic phase-in 1993–1996; modern items Aug 2004; varies by company | ~3 months (Free) / 15 years (Commercial) | **1 Year Maximum (Free Tier)** | 1999–2020 (Abrupt 2020 cutoff) | Trailing 30–90 days (Free) |
| **Backtest 2019–2020 Feasibility** | **100% Feasible (Free API, verified cohort)** | Paid Institutional Add-on Required | **BLOCKED (1-Year Limit)** | Feasible for AAPL; Blocked for Cohort | **BLOCKED (30-day Limit)** |
| **Timestamp Precision** | Second (`acceptanceDateTime` UTC) + 1–3 min dissemination lag | Exact Second (`publishedDate` UTC) | UNIX Second (`datetime`) | Second / Hour (`published_at` UTC) | Second (`published_at` ISO) |
| **Text Content** | **Full Text (8-K Body + Ex 99.1 PR)** | Headline + Summary Only (No Body) | Headline + Summary Only (No Body) | Headline Only (100% Empty Body) | Headline + Snippet (No Body) |
| **Entity Mapping** | **100% Authoritative via SEC CIK** | Ticker String (Risk of Ticker Reuse) | Ticker String (Modern Survivorship Bias) | Ticker String (41% Match Rate) | Ticker / Entity Extraction |
| **Cost & Rate Limits** | **100% Free** (10 req/s with User-Agent) | Free (500 req/hr) / Power ($30/mo) | Free (60 req/min) / Paid ($50–$500/mo) | Free Download (Static Local Parquet) | Free (100 req/day) / Paid ($29+/mo) |

---

## 5. Licensing and Permitted-Use Evidence

We examined authoritative terms of service and legal statutes for each candidate source:

### 5.1 SEC EDGAR (Form 8-K & Corporate Exhibits)
- **Statutory Scope vs. Agency Dissemination Policy**:
  - *Statutory Rule (17 U.S.C. § 105)*: Under 17 U.S.C. § 101 and § 105, copyright protection is withheld only from *"work[s] of the United States Government"*, defined as works created by officers or employees of the US Federal Government as part of their official duties. Form 8-K filings, exhibits, and corporate press releases (Exhibit 99.1) are authored by **private companies, corporate officers, and public relations firms**—not by officers or employees of the US Government. Therefore, corporate filings cannot be declared unconditionally public domain under 17 U.S.C. § 105.
  - *SEC Administrative Policy*: The SEC's official [Webmaster Frequently Asked Questions](https://www.sec.gov/about/webmaster-frequently-asked-questions) states:
    > *"All government-created content on sec.gov and EDGAR public filing content are free to access and reuse. You generally do not need special permission to reuse government-created content or public filings found on EDGAR."*
  - *SEC Fair-Access Guidelines*: Users are permitted to access and cache EDGAR data provided requests do not exceed 10 requests per second and include a descriptive `User-Agent` header containing the user's organization and contact email address ([SEC Accessing EDGAR Data](https://www.sec.gov/os/accessing-edgar-data)).
- **Legal Boundaries & Unresolved Questions**:
  1. *Factual & Metadata Features*: Under the doctrine of *Feist Publications, Inc. v. Rural Telephone Service Co.* (499 U.S. 340), purely factual disclosure metadata (filing dates, accession numbers, Item numbers, numerical financial disclosures) is non-copyrightable. Ingesting, caching, and engineering statistical event features from 8-K filings is **VERIFIED_ALLOWED**.
  2. *Third-Party & Corporate-Authored Full Text*: Corporate press releases (Exhibit 99.1) and embedded commercial graphics/contracts may carry underlying corporate copyrights. While accessing and analyzing filings for research is widely protected under fair use, **commercial redistribution of raw text or commercial AI model training on full-text corporate exhibits remains legally unresolved (UNVERIFIED / RESTRICTED)**. Public accessibility on EDGAR does not constitute an express waiver of private intellectual property rights or an unconditional commercial license.
- **Classification**:
  - Structured filing metadata, local research caching, and derived statistical features: **VERIFIED_ALLOWED**.
  - Bulk commercial redistribution of raw corporate-authored exhibits or commercial AI model training: **RESTRICTED / UNVERIFIED**.

### 5.2 Tiingo Financial News
- **Terms of Service**: [`https://www.tiingo.com/about/terms`](https://www.tiingo.com/about/terms) (Checked: October 2026).
  - Section 3 & Schedule A: Standard individual accounts (Free Starter, Power) grant a license for **"Internal Use Only"**. Internal use is defined as personal use; users may not display, redistribute, or share the data with third parties.
  - Commercial solicitation, powering external commercial software, or training models for commercial sale requires an explicit **Commercial / Enterprise License**.
  - Local warehousing of bulk news feeds is prohibited under the Starter Tier without enterprise data rights.
- **Classification**: **RESTRICTED** on Starter Tier (in-memory derivative statistical features permitted; persistent text warehousing and commercial model deployment prohibited).

### 5.3 Finnhub Company News
- **Terms of Service & Pricing**: [`https://finnhub.io/terms-of-service`](https://finnhub.io/terms-of-service) and [`https://finnhub.io/pricing`](https://finnhub.io/pricing) (Checked: October 2026).
  - Free Tier ($0/month) is restricted to **Personal Non-Commercial Use**.
  - The **Company News endpoint on the Free Tier is restricted to a maximum of 1 year of historical news**.
  - Redistribution, automated scraping of underlying articles, and commercial deployment require enterprise agreements ($500+/month).
- **Classification**: **NOT_ALLOWED for historical backtesting** (1-year depth restriction renders 2019–2020 backtesting impossible on the free plan); **RESTRICTED** for non-commercial personal real-time use.

### 5.4 FNSPID (Financial News and Stock Price Integration Dataset)
- **Provenance & Documentation**: Zenodo [`https://doi.org/10.5281/zenodo.8149400`](https://doi.org/10.5281/zenodo.8149400) and Hugging Face [`Zihan1004/FNSPID`](https://huggingface.co/datasets/Zihan1004/FNSPID).
  - Academic authors published under CC-BY 4.0. However, the underlying dataset consists of scraped articles from commercial publishers (Bloomberg, Reuters, Benzinga, Nasdaq).
  - Because upstream publishers did not grant redistribution licenses to the dataset creators, the legal right to persist, redistribute, or train commercial models on this raw text cannot be confirmed.
- **Classification**: **UNVERIFIED**. Must remain strictly isolated from authorized production/training pipelines.

---

## 6. Historical Coverage & Timestamp Quality Assessment

### 6.1 Timestamp Precision and Point-in-Time Availability Boundaries

| Source | Raw Field Name | Raw Format Example | Normalized Type | Sub-Daily Intraday? | Availability Boundary Rule | Lookahead Risk |
| :--- | :--- | :--- | :--- | :---: | :--- | :---: |
| **SEC Form 8-K** | `acceptanceDateTime` | `"2020-01-29T16:30:12.000Z"` | `timestamp[us, UTC]` | **YES (Second)** | Available when $T_{\text{acceptance}} + \Delta_{\text{lag}} \le T_{\text{decision}}$ ($\Delta_{\text{lag}} \ge 5\text{m}$) | **Low (Qualified)** (1–3 min dissemination lag) |
| **Tiingo News** | `publishedDate` | `"2020-03-12T14:22:00.000Z"` | `timestamp[us, UTC]` | **YES (Second)** | Available when $T_{\text{published}} \le T_{\text{decision}}$ | Low (Vendor latency) |
| **Finnhub News** | `datetime` | `1583936520` (UNIX s) | `timestamp[us, UTC]` | **YES (Second)** | Available when $T_{\text{published}} \le T_{\text{decision}}$ | Low (Vendor latency) |
| **FNSPID** | `date` | `"2020-03-09 00:00:00"` | `timestamp[us, UTC]` | Mixed / Artificial | Coarse midnight stamps must be delayed to $T+1$ | **High** (Date-only trap) |

### 6.2 The "Date-Only Midnight Trap" & Same-Day Leakage Prevention
In commercial and academic news feeds, articles frequently report date-only stamps (e.g. `"2020-04-15"`).
- Normalizing `"2020-04-15"` to `2020-04-15 00:00:00 UTC` creates an acute look-ahead hazard: a decision formulated at 09:30 EDT (13:30 UTC) would assume the article was available before the market open, even though it may have been published after market close at 17:00 EDT.
- **Enforced Policy in `NewsFeatureEngine`**:
  $$\text{If } \text{has\_intraday\_time} == \text{False}, \quad \text{Article is eligible ONLY if } \text{published\_date} < \text{decision\_date}$$
  Date-only articles are strictly masked on the publication date itself and become available only on the subsequent trading date ($T+1$).

### 6.3 Handling Weekend, Holiday, and After-Hours Publications
1. **After-Hours News ($16:00 \le T_{\text{pub}} < 24:00$ ET)**: For a decision aligned with the next-session open ($09:30$ ET, with 15-minute pre-open buffer at $09:15$ ET), after-hours news from session $T$ is cleanly captured in the overnight trailing window and is eligible for session $T+1$ execution.
2. **Weekend & Holiday News**: Articles published between Friday 16:00 ET and Monday 09:15 ET are accumulated into trailing lookback windows ($W=1, 3, 7$ days) and become executable at Monday opening auction.
3. **Filing Acceptance vs Legal Filing Date (Regulation S-T Rule 13)**: Under SEC rules, an 8-K submitted after 17:30 ET receives the *next* business day as its legal `filingDate`. However, EDGAR records the exact ingestion second in `acceptanceDateTime`. Our pipeline uses `acceptanceDateTime`, ensuring that after-hours material disclosures are correctly known to pre-open decisions on the subsequent morning without artificial multi-day delays.

### 6.4 EDGAR Acceptance vs Dissemination Latency & Historical Coverage Realities
1. **Acceptance vs. Dissemination Latency**:
   - `acceptanceDateTime` records the timestamp when EDGAR's intake subsystem successfully validated the filing.
   - The SEC documents that public website and API dissemination to `sec.gov`, RSS feeds, and the Public Dissemination Service (PDS) feed follows acceptance by **1 to 3 minutes** (with variable delays during peak quarterly filing windows).
   - *Lookahead Leakage Qualification*: We cannot claim "zero lookahead leakage" based on raw `acceptanceDateTime` alone without accounting for dissemination latency. For backtesting, a reproducible availability rule must apply an availability buffer $\Delta_{\text{lag}} \ge 5\text{ minutes}$. In our existing architecture, the `NEXT_SESSION_OPEN` pre-open cutoff buffer (`pre_open_cutoff_minutes = 15`, cutting off at 09:15 ET for a 09:30 ET open) comfortably absorbs this 1–3 minute dissemination lag.
2. **EDGAR Historical Coverage Realities**:
   - *Phase-In of Electronic Filing (1993–1996)*: While EDGAR began pilot operations in 1994, mandatory electronic filing for US public companies was phased in under Rule 101 of Regulation S-T between April 1993 and May 1996. Pre-phase-in records were submitted on paper and are absent from digital EDGAR.
   - *August 2004 Form 8-K Overhaul (Release No. 33-8400)*: The SEC restructured Form 8-K in August 2004, establishing the modern item numbering system (Items 1.01, 2.02, 5.02, 7.01, etc.). Prior to August 2004, 8-K items used completely different numbering (e.g. Item 5 = Other Events, Item 7 = Financial Statements & Exhibits).
   - *Exhibit 99.1 Press Releases*: Attaching full press releases under Exhibit 99.1 became widespread only after Regulation FD (Fair Disclosure) in October 2000 and the 2004 Form 8-K amendments.
   - *Company-Specific Inception Dates*: Modern S&P 500 constituents that completed IPOs after 1994 (e.g., Alphabet/Google in 2004, Tesla in 2010, Meta/Facebook in 2012) possess zero EDGAR filings prior to their respective registration statements. Universal 8-K coverage cannot be assumed from 1994 across all constituents. Phase 5F must verify historical filing spans per cohort company.

---

## 7. Company Identity & Pilot Coverage Assessment

### 7.1 Entity Resolution Against the Verified Cohort

| Ticker | Canonical Company ID | SEC CIK | SEC 8-K Coverage | Tiingo Coverage | Finnhub Free Coverage | FNSPID Coverage |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AAPL** | `US_CIK_0000320193` | `0000320193` | **102 8-Ks in local JSON** (1994–2026) | Trailing ~3 months only | Trailing 1 year only | **441 articles** (Mar–Jun 2020) |
| **JPM** | `US_CIK_0000019617` | `0000019617` | **25 8-Ks in local JSON** (2025–2026) | Trailing ~3 months only | Trailing 1 year only | **0 articles (Missing)** |
| **GOOG** | `US_CIK_0001652044` | `0001652044` | Complete on EDGAR (CIK available) | Trailing ~3 months only | Trailing 1 year only | **0 articles (Missing)** |
| **TSLA** | `US_CIK_0001318605` | `0001318605` | Complete on EDGAR (CIK available) | Trailing ~3 months only | Trailing 1 year only | **0 records (Missing)** |
| **AA** | `UNKNOWN_AA` | None | Ambiguous (Alcoa corporate split) | Ticker string collision | Ticker string collision | **2,697 articles (Unmapped)** |

### 7.2 Resolution of Ticker Ambiguity (`AA` Case Study)
Ticker `AA` historically represented Alcoa Inc. In November 2016, Alcoa Inc. executed a tax-free corporate spinoff:
- The upstream bauxite, alumina, and aluminum smelting business became **Alcoa Corporation** (new SEC CIK `0001675149`, retaining ticker `AA`).
- The downstream engineered products and aerospace business was renamed **Arconic Inc.** (retaining the original historical CIK `0000004281`, changing ticker to `ARNC`).
- Mapping all historical `AA` news or market records to modern Alcoa Corporation creates severe entity contamination.
- **Enforced Policy**: Ticker `AA` remains strictly excluded from multi-company training cohorts until point-in-time succession mapping is verified.

---

## 8. Point-in-Time Leakage and Deduplication Risks

### 8.1 Deduplication Architecture
- In commercial news aggregators, syndicated wire stories (e.g. PR Newswire, Business Wire, Dow Jones) are republished simultaneously by dozens of outlets with identical or trivially edited headlines.
- Counting duplicate syndicated articles creates synthetic volatility in news volume features (`news_count_trailing_1d`).
- **Deterministic Identifier**: Our schema enforces:
  $$\text{news\_id} = \text{SHA-256}(\text{ticker} + \text{published\_at} + \text{source} + \text{url} + \text{headline})[:24]$$
- **Syndication Clustering**: When identical headlines appear across multiple publishers within a 60-minute window, `NewsFeatureEngine` provides a deduplication filter (`deduplicate_headlines = True`) to prevent article count inflation while preserving publisher provenance.

### 8.2 Backfilled and Revised Records
- Commercial news APIs often update article timestamps when editorial corrections, typo fixes, or market close wrap-ups are added hours after original publication.
- Relying on the updated timestamp can cause a morning article to appear as an evening article (or vice versa).
- **Defense**: Store `original_timestamp_raw` alongside parsed `published_at`, and record `ingestion_timestamp`. Discard or quarantine articles whose timestamps are retroactively modified by vendors during historical backfills.

---

## 9. Recommended Primary Source and Fallback

### 9.1 Recommended Primary Event Layer: SEC Form 8-K Disclosures (with Qualified Exhibit Rationale)
- **Why**:
  1. **Legal Clearance for Metadata & Factual Features**: Structured corporate disclosures and filing metadata are fully accessible and reusable under SEC dissemination policies and the *Feist* doctrine. Local caching and derived statistical event counts (`sec_event_count_5d`, `sec_days_since_last_8k`) are **VERIFIED_ALLOWED**.
  2. **Qualified Full-Text Intellectual Property Rights**: Commercial model training on corporate-authored text (Exhibit 99.1 press releases) or bulk commercial redistribution carries unresolved copyright questions under private corporate authorship. It must remain classified as **RESTRICTED / UNVERIFIED** for commercial deployment until explicit licensing or judicial fair use standards are established.
  3. **Point-in-Time Integrity with Dissemination Buffer**: Second-level `acceptanceDateTime` combined with a conservative $\ge 5$-minute buffer (absorbed by our 15-minute pre-open buffer) provides a robust temporal cutoff without claiming unverified zero-second instant dissemination.
  4. **Multi-Company Feasibility**: Available across active and historical S&P 500 constituents via official EDGAR REST APIs without subscription paywalls, subject to company-specific registration/IPO dates.
  5. **High-Fidelity Material Events**: Covers substantive corporate events (earnings releases under Item 2.02, guidance under Item 7.01, executive changes under Item 5.02, M&A under Item 1.01).

### 9.2 Recommended Auxiliary Fallback: Tiingo News API (In-Memory Trailing Features)
- **Role**: Supplemental real-time news headlines for active forward paper-trading.
- **Restrictions**: Must execute in in-memory mode (`storage_authorized = False`). Cannot be persisted to disk without enterprise licensing.

### 9.3 Formally Rejected Sources:
- **FNSPID**: Rejected as primary training corpus (75% cohort missingness, 100% empty bodies, unverified publisher copyright).
- **Finnhub Free Tier**: Rejected for historical backtesting (hard 1-year historical lookback cap).

---

## 10. Explicit Unresolved Questions & Required Evidence

| Unresolved Item | Core Risk / Uncertainty | Evidence Required to Resolve |
| :--- | :--- | :--- |
| **8-K Exhibit 99.1 Extraction Automation** | Exhibit 99.1 press releases are formatted in HTML/ASCII within filing packages (`.htm`/`.txt`). Automated HTML stripping and text cleaning must preserve table structures without corrupting NLP embeddings. | Benchmark parser on 50 representative 8-K filings across diverse filing agents (RR Donnelley, Toppan, Broadridge). |
| **Event Sparsity over Short Horizons** | Companies file Form 8-K filings only 10–25 times per year. Over a 5-trading-session horizon, 80%+ of weekly intervals may have 0 material announcements. | Measure event frequency across the full S&P 500 panel and evaluate binary event flags vs decay-weighted recency features. |
| **Tiingo Commercial Enterprise Cost** | Transitioning from personal research to commercial deployment of aggregated news requires enterprise pricing. | Direct vendor quotation from Tiingo sales establishing pricing for S&P 500 news archiving rights. |
| **Historical Entity Disambiguation for `AA`** | Ticker `AA` historical transition to `ARNC` in November 2016 requires a definitive CIK-to-ticker mapping table covering corporate spin-offs. | Cross-reference CRSP/Compustat or SEC Form 8-K item 8.01 filings from October–November 2016 for Alcoa Inc. |

---

## 11. Minimal Next-Phase Implementation Plan (Phase 5F Preview)

To introduce textual intelligence into the project safely and legally, the next phase must follow this bounded plan:

1. **Build SEC Form 8-K Metadata Extractor**:
   - Reuse existing `SECFetcher` to parse `filings.recent` from `data/raw/sec/submissions/CIK{cik}.json`.
   - Filter to Form 8-K filings with items of interest (Item 1.01, 2.02, 5.02, 7.01, 8.01).
   - Extract `accessionNumber`, `filingDate`, `acceptanceDateTime`, `items`, and document URLs.
2. **Normalize into Canonical News Schema**:
   - Map 8-K filings into `PROCESSED_NEWS_SCHEMA` with:
     - `published_at = acceptanceDateTime`
     - `has_intraday_time = True`
     - `source = "sec_edgar_8k"`
     - `headline = "Form 8-K: " + items_description`
3. **Generate Point-in-Time Corporate Event Features**:
   - Compute trailing event count (`sec_event_count_1d`, `sec_event_count_5d`, `sec_event_count_21d`).
   - Compute earnings release flag (`sec_earnings_release_in_window`).
   - Compute filing recency (`sec_days_since_last_8k`).
4. **Acceptance Criteria**:
   - 100% passing unit tests proving point-in-time availability isolation with conservative dissemination buffer ($T_{\text{acceptance}} + \Delta_{\text{lag}} \le T_{\text{decision}}$, $\Delta_{\text{lag}} \ge 5\text{m}$).
   - 100% legal clearance under `StoragePolicy` and SEC Webmaster FAQ guidelines for structured disclosure metadata and statistical feature extraction.
   - Empirical per-company filing coverage verification confirming active 8-K reporting across all evaluated cohort entities during the target historical window (2019–2020).
   - Zero paid API keys, secrets, or unauthorized disk writes.

---

## 12. Audit Traceability: Files Inspected and Files Changed

### Files Inspected (Read-Only):
- `data/processed/news/fnspid_news_processed.parquet`
- `data/processed/news/fnspid_news_processed_validation_report.json`
- `data/raw/news/fnspid_all_external_sample.csv`
- `data/raw/sec/submissions/CIK0000320193.json`
- `data/raw/sec/submissions/CIK0000019617.json`
- `src/data/market/storage_policy.py`
- `src/data/news/schema.py`
- `src/data/news/ingestor.py`
- `src/features/news.py`
- `src/features/config.py`
- `src/features/dataset.py`
- `docs/phase2_fnspid_report.md`
- `docs/phase3a_data_source_research.md`
- `docs/phase4b_news_pipeline_report.md`
- `docs/phase5_training_dataset_readiness_report.md`

### Files Changed / Produced:
- `docs/phase5e_news_source_licensing_audit_report.md` (This report — Documentation Deliverable)
- *Zero production code, test code, or data files were modified in Phase 5E.*
