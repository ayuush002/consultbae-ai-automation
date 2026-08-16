# Data Quality and Merge Report

## Executive summary

The three supplied CSV files contained 105 source rows. The ingestion pipeline accepted 103 rows, automatically repaired 1 shifted row, rejected 2 non-data rows, and produced 56 unique candidate records. In total, 47 duplicate source records were consolidated.

| Metric | Result |
|---|---:|
| Raw source rows | 105 |
| Accepted rows | 103 |
| Automatically repaired rows | 1 |
| Rejected rows | 2 |
| Unique candidates | 56 |
| Duplicate rows merged | 47 |
| Candidates represented by multiple rows | 31 |

Accepted rows by source were: 42 from Naukri, 31 from gig workers, and 30 from CBNexus.

## Issues found and handling decisions

### Different schemas

Each source described the same person using different column names and attributes. For example, the sources used `Full Name`, `worker_name`, and `Name`, while phone fields appeared as `Phone` and `Phone Number`.

The pipeline maps each known source schema to a canonical candidate model. It also accepts documented column aliases and ignores harmless extra columns. A missing required column causes the run to stop before the database is changed, preventing silent corruption.

### Email inconsistencies

Emails contained capitalization and surrounding whitespace. They were trimmed, converted to lowercase, and checked against a basic email structure. Invalid values become null and are not used as identity keys.

### Phone inconsistencies

Phone numbers used spaces, punctuation, and country-code variants. The pipeline removes non-digits, retains the final 10 digits, and accepts only plausible Indian mobile numbers beginning with 6–9. Invalid values become null or cause rejection when the source requires a phone.

### City aliases

Equivalent locations appeared under different names, including Bangalore/Bengaluru, Gurgaon/Gurugram, and Delhi/New Delhi/Delhi NCR. These are mapped to canonical city names. Other non-empty locations are trimmed and title-cased.

### Mixed dates

Application dates used multiple formats: ISO, day-first with hyphens, US-style slash dates, and textual month dates. Valid dates are stored in ISO `YYYY-MM-DD` format. Unparseable optional dates become null.

### Mixed compensation units

Naukri CTC values mixed lakh-style values with full annual amounts. Values below 100 are interpreted as lakhs and multiplied by 100,000; larger values are retained as annual currency amounts.

Gig rates combined numeric values, optional `k`, and `/hr` or `/month`. These are separated into `rate_amount` and `rate_period` so hourly and monthly rates are never compared as if they were the same unit.

### Skills formatting

Comma-separated skills varied in capitalization. Values are trimmed, deduplicated, sorted, and mapped to consistent display names such as `JavaScript`, `FastAPI`, `MySQL`, and `REST APIs`.

### Verification and status values

CBNexus verification values are normalized to true, false, or unknown. Gig-worker status is lowercased and validated against `active`, `inactive`, and `paused`.

### Structurally invalid rows

Two rows were rejected and retained in the `rejected_rows` audit table:

| Source | CSV row | Reason |
|---|---:|---|
| gig_workers | 12 | Completely blank row |
| cbnexus | 16 | Repeated header row inside the data |

One gig-worker row (CSV row 20) had values shifted into the wrong columns. Its pattern was unambiguous, so the row was repaired automatically and marked with `was_repaired = 1` in `candidate_sources`.

## Duplicate resolution

Records are connected when they share a normalized email or normalized phone. A normalized name-plus-city key is used only when that combination is not repeated within any single source; this safeguard reduces the risk of merging two different people who share a common name and city.

Connected records are resolved transitively. For example, if record A matches B by email and B matches C by phone, all three are treated as one candidate. This is implemented with a union-find data structure.

For each merged candidate, the pipeline preserves:

- A canonical set of candidate fields.
- The union of normalized skills.
- A list of contributing data sources.
- The number of source rows represented.
- Every original row, its source, its CSV row number, and whether it was repaired.

The largest merged identity contained four source rows. The final distribution was 25 candidates with one source row, 16 with two, 14 with three, and 1 with four.

## Database design and auditability

The generated SQLite database contains:

- `candidates`: one canonical row per resolved person.
- `candidate_sources`: lineage back to every accepted raw row.
- `rejected_rows`: rejected input and the reason for rejection.

Indexes on canonical email and phone support fast duplicate checks by the API and n8n workflow.

## Known limitations

- Email validation checks structure but does not verify that a mailbox exists.
- Phone validation is tailored to 10-digit Indian mobile numbers.
- Name-plus-city matching remains heuristic and is deliberately conservative.
- When sources disagree on a non-identity field, the current version selects the first non-null value rather than applying source trust scores or recency rules.
- CTC conversion assumes small numeric values represent lakhs because the source provides no explicit unit column.

## Production recommendations

For a production-scale system, add configurable source schemas, country-aware phone parsing, stronger email validation, source-priority and recency rules, conflict flags for manual review, idempotent batch identifiers, database constraints, and monitoring for schema drift and rejection-rate changes.

The matching process should also record a confidence score and require human approval for uncertain name-based matches. Personally identifiable information should be encrypted, access-controlled, logged, retained only as necessary, and excluded from application logs.
