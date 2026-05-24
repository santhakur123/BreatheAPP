# MODEL.md — Data Model & Design Rationale

## Core Design Philosophy

The data model solves one problem: turning messy, heterogeneous source data into a single auditable table of emission events while preserving complete provenance. Every decision is traceable to "what does an auditor need?"

---

## Entity Map

```
Organisation  ──< OrganisationMembership >── User
     │
     ├──< IngestionBatch
     │         │
     │         └──< EmissionRecord >── EmissionRecordEditLog
     │
     └──< EmissionRecord (org FK for fast tenant filtering)
```

---

## Multi-Tenancy

**Strategy: Foreign-key tenancy on every queryable table.**

Every `EmissionRecord` and `IngestionBatch` has an `organisation` FK. Django queryset filtering (`filter(organisation=org)`) enforces tenant isolation at the ORM level, not the application level. This means a developer cannot accidentally leak data across tenants by forgetting a filter — the view's `get_queryset()` always applies the org constraint first.

Why not row-level security in Postgres? That would require DB-level roles per tenant, which adds operational complexity we don't need at prototype scale. The FK approach is auditable and transparent.

`OrganisationMembership` adds a role (`admin`, `analyst`, `viewer`) so permission checks don't need a separate permissions table.

---

## Scope 1/2/3 Classification

GHG Protocol classification is fixed at ingestion time, not at query time:

| Category | Scope | Rationale |
|---|---|---|
| `fuel_diesel`, `fuel_petrol`, `fuel_natural_gas` | 1 | Direct combustion by the company |
| `electricity` | 2 | Purchased electricity from grid |
| `flight_*`, `hotel_stay`, `ground_transport`, `procurement` | 3 | Indirect value chain |

Classification is determined by the ingestion parser based on source type and material description. It is stored on the record, not computed at query time, so an analyst can override it if the parser was wrong — and the edit is logged.

---

## Source-of-Truth Tracking

Three fields on `EmissionRecord` together answer "where did this row come from, and was it ever touched?":

- `source_system` — the named system (e.g. "SAP ECC 6.0 / Flat File Export")
- `source_row_id` — the original primary key or document number in the source
- `raw_data` (JSONField) — a verbatim snapshot of the source row at ingestion time, never modified

The `batch` FK links back to `IngestionBatch`, which records filename, uploader, and timestamp.

`EmissionRecordEditLog` is append-only. Every field change writes a new row with old value, new value, editor, and timestamp. This is never deleted. An auditor can reconstruct the full history of any record.

---

## Unit Normalisation

SAP exports units in SAP internal codes (`L`, `GAL`, `KG`, `M3`, `TO`). Utility exports use `kWh`, `MWh`, or `kVAh`. Travel data uses `km`, `passenger-km`, or `nights`.

**Strategy: normalise at ingestion, record the conversion.**

- `activity_quantity` always stores the normalised, converted value
- `activity_unit` always stores the target unit (`litre`, `kWh`, `passenger-km`, `room-nights`)
- `unit_conversion_applied` (bool) flags that a conversion happened
- `unit_conversion_note` records the conversion formula (e.g. "GAL × 3.78541 → litre")

This means queries like "sum all diesel consumption" work without unit-awareness. The raw original quantity is preserved in `raw_data`.

**Special case: kVAh.** Apparent energy (kVAh) cannot be directly converted to real energy (kWh) without the power factor. We flag these records, estimate using PF=0.9, and store the assumption in `unit_conversion_note`. The `is_flagged` + `flag_reason` fields surface this for analyst review.

---

## Audit Trail

`is_locked` + `locked_at` + `locked_by` implement a one-way lock. Once locked:
- `partial_update` is blocked (returns 403)
- The `review` action is blocked
- Only an admin can unlock (not implemented in this prototype — noted in TRADEOFFS.md)

`EmissionRecordEditLog` is the full edit history. `reviewed_by` + `reviewed_at` + `review_note` record the analyst's sign-off decision.

---

## Emission Factor Storage

Emission factors are stored on the record at ingestion time (`emission_factor`, `emission_factor_source`). We do not store them in a separate table and join at query time.

**Why?** Emission factors change year-over-year (DEFRA updates annually). Storing the factor used at the time of ingestion means historical records don't silently change when factors are updated. An auditor can always verify: "this record used DEFRA 2023, factor 2.68 kg CO₂e/litre."

`co2e_kg` is computed as `activity_quantity × emission_factor` and stored. It is recomputed on save if either field changes (and the edit is logged).

---

## Indexes

```python
Index(fields=['organisation', 'scope', 'activity_date'])   # scope summary queries
Index(fields=['organisation', 'review_status'])             # analyst dashboard
Index(fields=['batch'])                                     # batch drill-down
Index(fields=['is_flagged'])                                # flagged records view
```

The `organisation` prefix on the first two indexes means the DB can skip the full scan and go straight to tenant data.

---

## What This Model Deliberately Does Not Handle

- **Subsidiary/location hierarchy** — `Organisation` is flat. Real clients need plant → site → subsidiary → parent. Noted in TRADEOFFS.md.
- **Emission factor versioning table** — factors are stored inline. A proper system would have a `EmissionFactor` table with `valid_from`/`valid_to` and an annual update workflow.
- **Double-counting detection** — if the same SAP document is uploaded twice, we create two records. Deduplication by `source_row_id` per batch is not implemented.
