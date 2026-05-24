# TRADEOFFS.md — Three Things I Deliberately Did Not Build

## 1. Duplicate Detection Across Batches

**What it is:** If a user uploads the same SAP export twice (or uploads a corrected version that overlaps with a previous upload), we currently create duplicate `EmissionRecord` rows. A real system would detect that `source_row_id` + `source_system` + `organisation` already exists and either reject the duplicate or flag it for analyst review.

**Why I skipped it:**
This is harder than it sounds. SAP document numbers (`BELNR`) are unique within an SAP client, but not across clients or export configurations. A corrected document might come with the same BELNR but different values — that's a legitimate update, not a duplicate. Distinguishing "true duplicate" from "corrected re-upload" requires a versioning concept that would take a day to design and test correctly.

**The right solution:** A `deduplicate_on_ingest` flag per batch, combined with a `(source_system, source_row_id, organisation)` unique constraint with a `is_superseded` soft-delete field. Not worth the complexity for a prototype where the analyst can spot-check duplicates in the records table.

---

## 2. Async Ingestion (Celery / Background Workers)

**What it is:** Currently, file upload and parsing happens synchronously in the Django request-response cycle. A large SAP export (10,000+ rows) will time out the HTTP request.

**Why I skipped it:**
Celery requires a message broker (Redis or RabbitMQ), a worker process, and deployment configuration for both. That's three additional infrastructure components. For the scale of a prototype (hundreds of rows in the demo data), synchronous ingestion is fine. The `IngestionBatch.status` field is already designed to support async (`pending → processing → completed/failed`) — wiring it to Celery is a configuration change, not a schema change.

**The right solution:** Move `parse_sap_file`, `parse_utility_file`, `parse_travel_json` into Celery tasks, called from the upload view with `delay()`. The view immediately returns `{batch_id, status: "processing"}` and the frontend polls `GET /api/emissions/batches/{id}/` until status changes.

---

## 3. Hierarchical Organisation Structure (Sites, Subsidiaries, Reporting Boundaries)

**What it is:** Real enterprise clients don't have a single `Organisation` — they have a tree: Parent Company → Legal Entity → Country → Site → Building → Meter. GHG Protocol reporting requires knowing which legal entities are in the "operational control" boundary vs. "financial control" boundary.

**Why I skipped it:**
The assignment says "multi-tenancy" — I interpreted that as client isolation (one org per client), not internal hierarchy. Adding a hierarchy model would require:
- A `Site` or `Location` model with a parent FK
- Scope 1/2/3 classification might change depending on whether a site is owned, leased, or contracted
- Roll-up aggregation queries become recursive CTEs
- The analyst UX needs a tree navigator

This is the single most valuable thing to add after the prototype. The data model is designed to accommodate it: `EmissionRecord.activity_description` already stores plant/site string data, which could be parsed into a proper FK once the hierarchy model exists.

**The right solution:** Add a `Site(id, organisation, parent, name, boundary_type)` model. Add `site FK` to `EmissionRecord`. Update parsers to match plant codes / meter locations to site IDs. Update dashboard to group by site.
