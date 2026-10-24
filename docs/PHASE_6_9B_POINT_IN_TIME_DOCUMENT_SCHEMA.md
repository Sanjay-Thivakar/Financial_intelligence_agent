# PHASE 6.9B — POINT-IN-TIME FINANCIAL DOCUMENT SCHEMA & ALIGNMENT SPECIFICATION

**Document Version**: 1.0  
**Phase**: 6.9B Corrective Closeout  
**Target Ingestion Domain**: SEC EDGAR Filings (10-K, 10-Q, 8-K) and Textual Exhibits across 305-Company Cohort  
**Canonical Timezone Reference**: `America/New_York` normalized to UTC  

---

## 1. Objective and Anti-Leakage Invariants

In financial return prediction, multimodal models combine market prices with corporate financial statements, disclosures, and textual events. Any leakage of future information into historical decision points invalidates backtesting performance.

This specification defines the canonical schema, lineage requirements, and strict point-in-time eligibility invariants governing all financial documents and structured facts prior to feature extraction.

### Core Invariants
1. **Decision Cutoff Timestamp ($T_{\text{close}}$)**:  
   Predictions are evaluated at the close of trading session $T$ (16:00:00 `America/New_York`).
2. **Zero Look-Ahead Invariant**:  
   A document or fact is eligible to inform a prediction at trading session $T$ if and only if its public dissemination occurred strictly on or before session $T$ market close:
   $$\text{Eligible}(D, T) \iff D.\text{acceptance\_timestamp} \le T_{\text{close\_utc}}$$
3. **Restatement and Amendment Lineage**:  
   Subsequent amendments (e.g., Form 10-K/A or 10-Q/A) or restatements carry their own distinct `accession_number` and `acceptance_timestamp`. An amended value filed at $T_2 > T_1$ cannot overwrite or influence the historical value observed at $T_1$.
4. **Conservative Public Availability Fallback**:  
   If a record lacks microsecond or minute-level public acceptance timestamping, it cannot be assumed to have been available intraday on its filing date. It is conservatively quarantined until the subsequent trading session ($T+1$).

---

## 2. Canonical Document Schema Definition

Each ingested filing, document section, or exhibit is persisted as an immutable record conforming to the following schema:

| Column Name | Data Type | Nullable | Description & Constraints |
| :--- | :--- | :--- | :--- |
| `document_id` | String (UUIDv4) | No | Globally unique surrogate key for the document record. |
| `company_id` | String | No | Canonical universe company identifier (e.g., `US_EQ_0000097476`). |
| `ticker` | String | No | Primary cohort equity symbol (e.g., `TXN`). |
| `cik` | String(10) | No | SEC Central Index Key, zero-padded 10-digit string (e.g., `0000097476`). |
| `accession_number` | String(20) | No | SEC EDGAR unique filing identifier (e.g., `0001564590-18-010545`). |
| `form_type` | String | No | Filing form type (`10-K`, `10-Q`, `8-K`, `10-K/A`, `10-Q/A`, `8-K/A`). |
| `document_category` | String | No | Target section (`item_1a_risk_factors`, `item_7_mda`, `item_2_mda`, `exhibit_99_1_press_release`, `full_submission`). |
| `reporting_period_end` | Date (YYYY-MM-DD) | No | Fiscal period end date covered by the filing (e.g., `2018-03-31`). |
| `filing_date` | Date (YYYY-MM-DD) | No | Official EDGAR filing date recognized by SEC. |
| `acceptance_timestamp` | Timestamp (UTC) | No | Exact microsecond timestamp when SEC EDGAR servers accepted and disseminated filing (`acceptanceDateTime`). |
| `publication_timestamp` | Timestamp (UTC) | Yes | External wire service publication timestamp (for news/press releases); null if identical to acceptance timestamp. |
| `has_intraday_time` | Boolean | No | `True` if microsecond/second timestamp is verified; `False` if date-only. |
| `source_url` | String | No | Direct SEC EDGAR Archives URL to source document or exhibit. |
| `content_hash` | String(64) | No | SHA-256 cryptographic hash of extracted plain text payload. |
| `text_character_count` | Integer | No | Character length of extracted plain text payload. |
| `is_amendment` | Boolean | No | `True` if `form_type` ends with `/A`. |
| `amends_accession_number`| String(20) | Yes | Accession number of original filing amended by this filing; `null` if original. |
| `restatement_flag` | Boolean | No | `True` if document explicitly reports restated accounting facts for prior periods. |

---

## 3. Timezone Normalization and Session Close Synchronization

### Market Session Timing
The New York Stock Exchange (NYSE) and NASDAQ observe standard market hours:
- **Session Open**: 09:30:00 `America/New_York`
- **Session Close ($T_{\text{close}}$)**: 16:00:00 `America/New_York` (13:00:00 on scheduled early closes)

Because UTC does not observe Daylight Saving Time, `America/New_York` transitions between Eastern Standard Time (EST) and Eastern Daylight Time (EDT):

| Regime | Local Time Offset | Market Close in Local Time | Market Close in UTC ($T_{\text{close\_utc}}$) |
| :--- | :--- | :--- | :--- |
| **Eastern Standard Time (EST)** | UTC - 5 hours | 16:00:00 EST | **21:00:00 UTC** |
| **Eastern Daylight Time (EDT)** | UTC - 4 hours | 16:00:00 EDT | **20:00:00 UTC** |

### Conversion Invariant
Every market session $T$ is assigned an explicit, unambiguous UTC cutoff:
```python
import zoneinfo
import pandas as pd

def get_session_close_utc(session_date: pd.Timestamp) -> pd.Timestamp:
    """Computes exact UTC market close for trading session."""
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    # Scheduled close at 16:00:00 New York local time
    local_close = session_date.replace(hour=16, minute=0, second=0, microsecond=0, tzinfo=ny_tz)
    return local_close.astimezone(zoneinfo.ZoneInfo("UTC"))
```

---

## 4. After-Hours and Non-Trading Day Handling

### Scenario A: Intraday Filing During Market Hours
- **Event**: A Form 8-K is accepted by EDGAR at `14:15:22` EDT on Tuesday, 2019-04-16 (18:15:22 UTC).
- **Session Cutoff**: Session $T$ (2019-04-16) closes at `20:00:00` UTC.
- **Evaluation**: $18:15:22 \le 20:00:00 \implies$ **Eligible for Session $T$ feature snapshot**.
- **Model Action**: The model computing signals at session $T$ close may observe this filing.

### Scenario B: After-Hours Filing
- **Event**: An earnings release Form 8-K is accepted by EDGAR at `16:08:45` EDT on Tuesday, 2019-04-16 (20:08:45 UTC).
- **Session Cutoff**: Session $T$ (2019-04-16) closes at `20:00:00` UTC.
- **Evaluation**: $20:08:45 > 20:00:00 \implies$ **STRICTLY INELIGIBLE for Session $T$**.
- **Model Action**: The information was not publicly available to market participants prior to session $T$ close. It enters the feature store for the first time at session $T+1$ (Wednesday, 2019-04-17 close).

### Scenario C: Weekend or Market Holiday Filing
- **Event**: A filing is accepted by EDGAR on Saturday, 2019-04-20 at `11:00:00` UTC.
- **Session Cutoff**: Next trading session is Monday, 2019-04-22 (session close `20:00:00` UTC).
- **Evaluation**: Ineligible for any prior session; enters features for Monday session $T$ close.

### Scenario D: Date-Only / Missing Intraday Timestamps (Conservative Fallback)
- **Condition**: `has_intraday_time == False`.
- **Rule**: If the exact release second cannot be definitively established, the filing cannot be used on the same calendar day:
  $$\text{Eligible}(D, T) \iff D.\text{filing\_date} < T.\text{session\_date}$$
  This prevents any same-day intraday lookahead leakage.

---

## 5. Lineage and Accession Tracking for Structured Facts

When extracting XBRL accounting facts (e.g., `Revenues`, `NetIncomeLoss`, `Assets`):
1. **Fact-to-Filing Binding**: Every numeric fact must store the parent filing's `accession_number`.
2. **Acceptance Timestamp Join**: The fact inherits the `acceptance_timestamp` of its parent accession number from the SEC submissions feed.
3. **As-Of Querying**:
   ```sql
   SELECT concept, value, period_end, accession_number
   FROM financial_facts
   WHERE company_id = :target_company
     AND acceptance_timestamp <= :session_close_utc
   ORDER BY period_end DESC, acceptance_timestamp DESC
   LIMIT 1;
   ```
4. **Restatement Isolation**: A restatement filed months later has a later `acceptance_timestamp`. Therefore, an as-of query executed at historical time $T$ naturally retrieves the original reported value that historical market participants actually witnessed, rather than the revised restatement.
