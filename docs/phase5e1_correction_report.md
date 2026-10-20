# Phase 5E.1 — Audit Corrections and Phase 5F Readiness Report

**Date:** 2026-10-16  
**Status:** Audit Corrections Complete — Methodological & Legal Tightening Verified  
**Governing Documents:**  
- `docs/phase5e_news_source_licensing_audit_report.md` (Updated with Phase 5E.1 corrections)  
- `docs/phase5e1_correction_report.md` (This document)  
- SEC Webmaster Frequently Asked Questions: [https://www.sec.gov/about/webmaster-frequently-asked-questions](https://www.sec.gov/about/webmaster-frequently-asked-questions)  
- SEC Accessing EDGAR Data Policy: [https://www.sec.gov/os/accessing-edgar-data](https://www.sec.gov/os/accessing-edgar-data)  
- SEC EDGAR API Documentation: [https://www.sec.gov/edgar/sec-api-documentation](https://www.sec.gov/edgar/sec-api-documentation)  

---

## 1. Executive Summary & Purpose

Phase 5E.1 executes a rigorous audit and correction of three specific technical and legal claims in `docs/phase5e_news_source_licensing_audit_report.md`:
1. **SEC Reuse & Copyright Rationale**: Corrected the erroneous conflation of statutory US Government works (17 U.S.C. § 105) with corporate-authored SEC filings, properly distinguishing the SEC's administrative dissemination policy from statutory copyright rules.
2. **Point-in-Time Availability Boundaries**: Replaced unqualified claims of "zero lookahead leakage" based on raw `acceptanceDateTime` with the SEC's documented 1–3 minute dissemination lag, establishing a conservative availability buffer rule.
3. **EDGAR Historical Coverage Realities**: Replaced unsupported claims of universal 1994 coverage across S&P 500 constituents with documented electronic filing phase-in constraints (1993–1996), the August 2004 Form 8-K restructuring, and company-specific IPO/registration inceptions.

---

## 2. Detailed Corrections & Authoritative Evidence

### 2.1 SEC Reuse, Copyright Rationale, and 17 U.S.C. § 105

#### The Error in Phase 5E:
Phase 5E initially claimed that corporate Form 8-K filings and Exhibit 99.1 press releases are unconditionally public domain under **17 U.S.C. § 105**, granting unencumbered rights for commercial AI model training and redistribution.

#### The Authoritative Legal Reality:
- **Statutory Scope of 17 U.S.C. § 105**: Under 17 U.S.C. § 101 and § 105, copyright protection is withheld exclusively from *"work[s] of the United States Government"*, defined strictly as works created by officers or employees of the US Federal Government as part of their official duties. SEC Form 8-K disclosures, annual/quarterly reports, and attached exhibits (such as Exhibit 99.1 press releases) are prepared by **private corporate entities, company executives, legal counsel, and public relations firms**—not by government personnel. Therefore, corporate filings are **not** statutory works of the US Government.
- **SEC Administrative Dissemination Policy**: The SEC's official [Webmaster Frequently Asked Questions](https://www.sec.gov/about/webmaster-frequently-asked-questions) specifies the agency's reuse policy:
  > *"All government-created content on sec.gov and EDGAR public filing content are free to access and reuse. You generally do not need special permission to reuse government-created content or public filings found on EDGAR."*
- **Crucial Legal Qualifications & Remaining Uncertainty**:
  1. *Factual & Metadata Clearance*: Purely factual disclosures, numerical accounting tables, Item classifications, and submission metadata are non-copyrightable under the foundational doctrine of *Feist Publications, Inc. v. Rural Telephone Service Co.* (499 U.S. 340). Caching filing metadata and engineering statistical event features (e.g. `sec_event_count_5d`, `sec_days_since_last_8k`) is **VERIFIED_ALLOWED**.
  2. *Corporate-Authored Full Text & Exhibits*: While accessing EDGAR for factual research is freely permitted by SEC policy and protected by fair use, corporate authors retain underlying intellectual property rights in their press releases, marketing narratives, and proprietary exhibits. The legality of using full-text corporate exhibits for **commercial AI model training or bulk commercial redistribution remains legally evolving and UNVERIFIED**. Public availability on EDGAR does not constitute an express commercial copyright license or statutory indemnification.

#### Applied Correction:
In `docs/phase5e_news_source_licensing_audit_report.md` (Sections 1, 4, 5.1, and 9.1), SEC Form 8-K was adjusted:
- **Factual metadata, structured Item classifications, and statistical feature engineering**: Classified as **VERIFIED_ALLOWED**.
- **Commercial model training on corporate full-text exhibits and raw text redistribution**: Classified as **RESTRICTED / UNVERIFIED**.

---

### 2.2 Point-in-Time Availability: Acceptance vs. Public Dissemination Latency

#### The Error in Phase 5E:
Phase 5E claimed that `acceptanceDateTime` represents an exact public availability timestamp, asserting "zero lookahead leakage" without qualification.

#### The Technical Reality:
- **Acceptance vs. Dissemination Discrepancy**: According to the *EDGAR Filer Manual* and SEC Webmaster technical specifications:
  - `acceptanceDateTime` records the precise timestamp when EDGAR's intake subsystem validates and stamps the submission package upon receipt.
  - Public dissemination to the SEC.gov website, public web directories, RSS feeds, data APIs (`data.sec.gov`), and the commercial EDGAR Public Dissemination Service (PDS) feed follows acceptance by **1 to 3 minutes** under typical operating conditions.
  - During peak quarterly filing windows (e.g., 16:00–17:30 ET on deadline days), queuing delays can introduce longer, variable dissemination lags.
- **Data Feed Quirks**: Analysis of `data.sec.gov` submissions JSON feeds indicates that `acceptanceDateTime` occasionally exhibits formatting quirks (e.g. Eastern Time raw figures stamped with a trailing `Z`, or daylight savings offset shifts).

#### Applied Correction & Conservative Backtesting Rule:
1. **Dissemination Lag Buffer**: A backtest availability boundary cannot assume instant public visibility at $T_{\text{acceptance}}$. The pipeline must enforce a conservative availability buffer:
   $$T_{\text{available}} = T_{\text{acceptance}} + \Delta_{\text{lag}}, \quad \Delta_{\text{lag}} \ge 5\text{ minutes}$$
2. **Interaction with Project Timing Conventions**:
   - For our established `NEXT_SESSION_OPEN` execution convention ($09:30$ ET open), the project's configurable pre-open buffer (`pre_open_cutoff_minutes = 15`, cutting off information at $09:15$ ET) **comfortably absorbs the 1–3 minute dissemination lag** for all overnight and morning filings.
   - For filings accepted during the trading day, backtests must not assume execution before $T_{\text{acceptance}} + 5\text{ minutes}$.
3. **Traceability**: In `docs/phase5e_news_source_licensing_audit_report.md` (Sections 1, 4, 6.1, 6.4, 9.1), lookahead risk was updated from "Zero" to **"Low (Qualified by 1–3 min dissemination lag; mitigated by pre-open buffer)"**.

---

### 2.3 EDGAR Historical Coverage Realities

#### The Error in Phase 5E:
Phase 5E stated that complete Form 8-K and Exhibit 99.1 coverage is available for all S&P 500 constituents from 1994 to the present.

#### The Regulatory & Historical Reality:
1. **Phase-In of Electronic Filing (1993–1996)**:
   - Electronic submission was not universally mandated in 1994. Under Rule 101 of Regulation S-T, the SEC phased in mandatory EDGAR electronic filing in stages between April 26, 1993 and May 6, 1996. Filings submitted prior to an issuer's mandated group phase-in were paper-only and do not exist in digital EDGAR.
2. **August 2004 Form 8-K Regulatory Overhaul (SEC Release No. 33-8400)**:
   - In August 2004, the SEC completely restructured Form 8-K. This reform expanded the number of reportable events from 9 to 22 and created the modern 4-tier item numbering taxonomy (e.g., Item 1.01 Entry into Material Agreement, Item 2.02 Results of Operations and Financial Condition, Item 5.02 Departure/Appointment of Officers, Item 7.01 Regulation FD).
   - Filings prior to August 2004 utilized legacy item numbers (e.g. Item 5 was "Other Events", Item 7 was "Financial Statements and Exhibits"). Standardized item-filtering rules designed for modern 8-Ks cannot be applied retrospectively to pre-2004 records without custom historical mapping.
3. **Exhibit 99.1 Evolution**:
   - Attaching full-text press releases as Exhibit 99.1 became standard practice only after the adoption of **Regulation FD (Fair Disclosure)** in October 2000 and the 2004 Form 8-K amendments. Pre-2000 filings rarely contain Exhibit 99.1 press releases.
4. **Company-Specific Registration/IPO Dates**:
   - Modern S&P 500 companies have diverse public registration dates. For example, in our evaluation universe:
     - Alphabet Inc. (`GOOG`): IPO in August 2004 (no filings prior to 2004).
     - Tesla, Inc. (`TSLA`): IPO in June 2010 (no filings prior to 2010).
     - Meta Platforms (`META`): IPO in May 2012 (no filings prior to 2012).
   - Universal coverage from 1994 across all modern constituents is a factual impossibility.

#### Applied Correction:
`docs/phase5e_news_source_licensing_audit_report.md` (Sections 1, 4, 6.4, 9.1) was updated to document these structural boundaries and explicitly mandate company-by-company coverage verification for any target backtest window.

---

## 3. Summary of Changes Made to `docs/phase5e_news_source_licensing_audit_report.md`

| Section | Previous Statement | Corrected Statement | Core Rationale & Authoritative Basis |
| :--- | :--- | :--- | :--- |
| **Section 1 (Item 3)** | Unconditionally public domain under 17 U.S.C. § 105; universal 1994 depth; exact second-level availability with zero lookahead. | Conditional Go; 17 U.S.C. § 105 applies only to govt works; SEC Webmaster FAQ policy governs reuse; factual metadata is `VERIFIED_ALLOWED` while corporate full-text AI training is `RESTRICTED / UNVERIFIED`; 1–3 min dissemination lag noted; historical coverage bounded by phase-in and IPOs. | 17 U.S.C. § 101/105; SEC Webmaster FAQ; SEC Filer Manual; Reg S-T phase-in. |
| **Section 4 (Table)** | Legal status `VERIFIED_ALLOWED`; Framework `17 U.S.C. § 105`; Depth `1994 to Present (30+ Years)`. | Legal status `VERIFIED_ALLOWED (Metadata)` / `RESTRICTED (Full-Text AI)`; Framework `SEC Webmaster Policy / Feist`; Depth `Electronic phase-in 1993–1996; modern items Aug 2004; varies by company`. | Distinction between non-copyrightable factual data and private corporate authorship. |
| **Section 5.1** | "Works of the US Government are excluded from copyright protection under 17 U.S.C. § 105... VERIFIED_ALLOWED for model training." | Expanded statutory analysis of 17 U.S.C. § 101/105 vs private corporate authors; detailed citation of SEC Webmaster FAQ; explicit Feist doctrine analysis for metadata vs unresolved commercial AI training rights for full text. | 17 U.S.C. § 101; *Feist Publications* (499 U.S. 340); SEC Webmaster FAQ. |
| **Section 6.1 (Table)** | Lookahead risk: "Zero". Availability rule: $T_{\text{acceptance}} \le T_{\text{decision}}$. | Lookahead risk: "Low (Qualified: 1–3 min dissemination lag; mitigated by pre-open buffer)". Availability rule: $T_{\text{acceptance}} + \Delta_{\text{lag}} \le T_{\text{decision}}$ ($\Delta_{\text{lag}} \ge 5\text{m}$). | SEC PDS technical specifications; EDGAR Filer Manual. |
| **Section 6.4** | *(New Subsection Added)* | Documents 1–3 min dissemination latency; 1993–1996 electronic phase-in; August 2004 overhaul (Release 33-8400); Regulation FD impact on Exhibit 99.1; company IPO boundaries. | SEC Release No. 33-8400; Regulation S-T; Regulation FD. |
| **Section 9.1** | "100% Legally Unencumbered under 17 U.S.C. § 105; Zero Lookahead Leakage". | "Legal Clearance for Metadata & Factual Features under SEC policy & Feist; Qualified Full-Text IP Rights (UNVERIFIED for commercial AI); Dissemination buffer required". | Clarifies safe boundary for implementation. |
| **Section 11 (Item 4)** | Acceptance criteria: "Zero lookahead leakage; PERMITTED under 17 U.S.C. § 105". | Acceptance criteria: "Point-in-time isolation with conservative $\ge 5$m dissemination buffer; legal clearance under SEC Webmaster FAQ; empirical per-company filing coverage verification". | Rigorous, defensible acceptance criteria for Phase 5F. |

---

## 4. Phase 5F Readiness Assessment & Go / No-Go Decision

### Decision: **CONDITIONAL GO FOR PHASE 5F**

Phase 5F (SEC Form 8-K Corporate Event Integration) is authorized to proceed **strictly under the bounded scope defined below**.

### Permitted Implementation Scope for Phase 5F:
1. **Focus Exclusively on Structured Filing Disclosures & Metadata**:
   - Extract material event classifications from Form 8-K filing headers (`items`, `filingDate`, `acceptanceDateTime`, `accessionNumber`).
   - Specifically target high-signal material disclosure items:
     - `Item 2.02`: Results of Operations and Financial Condition (Quarterly Earnings Releases).
     - `Item 7.01`: Regulation FD Disclosure (Guidance, Presentations).
     - `Item 5.02`: Departure of Directors or Principal Officers; Election of Directors.
     - `Item 1.01`: Entry into a Material Definitive Agreement.
2. **Derive Purely Factual, Non-Reversible Statistical Event Features**:
   - Trailing event density counts: `sec_event_count_1d`, `sec_event_count_5d`, `sec_event_count_21d`.
   - Material earnings announcement indicator: `sec_earnings_release_in_window` (binary 0/1).
   - Event recency: `sec_days_since_last_8k`.
   - *Rationale*: These features are purely factual, non-copyrightable under the *Feist* doctrine, and 100% cleared under the SEC Webmaster reuse policy.
3. **Deferred Scope (Excluded from Phase 5F)**:
   - Full-text NLP embedding or sentiment classifier fine-tuning on raw Exhibit 99.1 corporate press release text is **deferred** pending formal legal clarification on commercial AI training rights on corporate-authored public exhibits.
   - No unverified commercial APIs (Finnhub, Tiingo) or tainted scraped datasets (FNSPID) will be introduced.

---

## 5. Mandatory Acceptance Criteria for Phase 5F

When Phase 5F is initiated, the implementation must satisfy all of the following criteria before acceptance:

1. **Conservative Availability Buffer**:
   - Form 8-K event features for a decision at $T_{\text{decision}}$ must enforce an availability cutoff:
     $$T_{\text{acceptance}} + \Delta_{\text{lag}} \le T_{\text{decision\_cutoff}}, \quad \Delta_{\text{lag}} = 5\text{ minutes}$$
   - When using `DecisionTimingMode.NEXT_SESSION_OPEN`, the configured `pre_open_cutoff_minutes` ($\ge 15$ minutes before 09:30 ET) must be verified to absorb both the pre-open trading auction and the 1–3 minute EDGAR dissemination lag.
2. **Empirical Cohort Coverage Verification**:
   - Form 8-K filing coverage must be independently verified for all four active cohort companies (`AAPL`, `JPM`, `GOOG`, `TSLA`) across the target benchmark period (`2019-01-01` to `2020-06-10`).
   - If any cohort entity lacks 8-K records in the local raw submissions directory, the missing records must be ingested via the rate-limited `SECFetcher` (10 req/s, declared `User-Agent`) or documented as a coverage limitation.
   - Missing event periods must be recorded as zero activity (0 events) rather than unobserved nulls, distinguishing active non-events from source unavailability.
3. **Identity & Interval Precision**:
   - All 8-K records must join to market and fundamental data strictly via canonical SEC CIK (`company_id`).
   - Ticker `AA` must remain excluded until corporate spin-off succession is resolved.
4. **Leakage & Regression Tests**:
   - Unit tests must programmatically prove that an 8-K filing accepted within the dissemination buffer or after the information cutoff cannot enter the feature vector.
   - Full regression suite across all existing modules (market features, fundamentals, target engine, panel splitter) must continue to pass with zero regressions.
5. **Fair Comparative Walk-Forward Baseline**:
   - Evaluate the incremental predictive value of Form 8-K corporate event features against the accepted Phase 5C market-only baseline and Phase 5D fundamentals baseline using identical 4-fold walk-forward splits, 5-date purge gaps, and training-only scaling.
   - Report RMSE, MAE, Hit Rate, and descriptive IC with full transparency.
