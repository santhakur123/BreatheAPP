# DECISIONS.md — Ambiguity Resolution & Design Choices

## SAP Source: Which Export Format?

**Ambiguity:** SAP exposes data via IDoc (EDI), OData services, BAPIs (RFC calls), and flat file exports. The assignment says "pick one and justify."

**Choice: SAP flat file export (tab-separated, SE16/custom report output)**

**Why:**
- The assignment says the sustainability team has data "sitting in SAP" — this implies a human is extracting it, not an automated integration. Flat files are what sustainability leads actually email around.
- IDoc requires EDI infrastructure and a receiving system. There is no EDI middleware in a 4-day prototype.
- OData/BAPIs require live SAP connectivity, credentials, and often a custom function module. Not realistic without an actual SAP sandbox.
- Flat file is the least glamorous choice and the most realistic one for an enterprise onboarding scenario.

**What I handle:**
- Tab-separated and semicolon-delimited exports
- German column headers (BUCHUNGSDATUM → BUDAT, MATERIALBEZEICHNUNG → MAKTX)
- SAP date format YYYYMMDD and European DD.MM.YYYY
- SAP unit codes (L, GAL, KG, M3, TO)
- Material description → fuel category matching (including German: Dieselkraftstoff, Benzin, Erdgas)
- Movement types not filtered (in production: filter to 201/261 consumption postings only)

**What I ignore:**
- MIGO/WM transaction codes — movement type filtering is commented in the parser but not enforced
- Cost centre hierarchy — KOSTL is stored in description, not parsed into a hierarchy
- Plant → legal entity mapping — PLANT_LOOKUP is a hardcoded dict; in production this is a DB table
- Currency — DMBTR and WAERS are stored in raw_data but not used for emission calculation

**What I'd ask the PM:**
- Which SAP modules are in scope? MM only, or also FI (CO2 allocations), PM (maintenance fuel), SD?
- Do they have a plant-to-legal-entity mapping? This matters for Scope 1 attribution.
- What movement types represent actual consumption vs. internal transfers?

---

## Utility Source: Which Mode?

**Ambiguity:** "PDF bill, portal CSV export, or API if the utility offers one."

**Choice: Portal CSV export**

**Why:**
- India (where this client appears to operate based on INR currency) has 50+ state DISCOMs. Almost none offer a Green Button or ESPI API. A few (like BESCOM in Bangalore) have a consumer portal where a facilities manager can export the last 12 months as CSV.
- PDF parsing is brittle — layout differs per utility, requires OCR for scanned bills, and the field positions change when utilities update their templates.
- CSV export is the realistic deliverable. Facilities teams already do this manually; we're just giving them a drop zone.

**Key complications handled:**
- Billing periods that don't align to calendar months (we store the reading date, not the period)
- kVAh vs kWh (flagged, estimated with PF assumption)
- MWh → kWh conversion
- Multiple meters per account (meter number in description)
- Tariff codes stored but not used in emission calculation (ToD peak/off-peak emission factor differentiation is out of scope)

**What I'd ask the PM:**
- Do they have multiple meters per site, or one meter per site?
- Are they on ToD tariffs? Peak vs. off-peak emission factors differ by ~15%.
- Which DISCOMs? Some (like MSEDCL) export a different column order than BESCOM.

---

## Travel Source: Which Platform and Format?

**Ambiguity:** "Concur, Navan, or similar."

**Choice: JSON export modelled on Navan's trip export structure**

**Why:**
- Navan's API returns trip data as nested JSON with a `segments` array — flights, hotels, ground transport as typed objects. This is the most common structure among modern travel platforms.
- Concur's TripIt integration also uses JSON. The schema is similar enough that our parser handles both with minor field aliasing.
- CSV flattening of multi-leg trips loses leg-level detail needed for per-segment emission factors.

**Key complications handled:**
- Distance not always provided: computed via haversine from IATA airport codes when missing (flagged)
- Cabin class: business class uses DEFRA's 3× higher emission factor
- Hotel stays: per room-night factor (DEFRA 2023: 31.2 kg CO₂e/night)
- Ground transport: per-km car rental factor as default (no rail-specific factor in this prototype)

**What I'd ask the PM:**
- Do they use Navan, Concur, or another platform? Are they willing to create an API key, or will they export manually?
- Do they have rail data? Rail emission factor is significantly lower than car.
- Is the data per-traveller or aggregated? Per-traveller data (with employee IDs) would enable department-level attribution.

---

## Review Workflow

**Ambiguity:** "Let analysts review and sign off before it goes to auditors."

**Choice:** Three-state workflow: `pending → approved/rejected/flagged`, then `locked`.

An `approved` record can be locked. A locked record cannot be edited or re-reviewed. This is the minimum viable audit gate.

**What I did not build:** email notifications when records are flagged, or a separate "auditor view" — noted in TRADEOFFS.md.

---

## Emission Factors

**Choice:** DEFRA 2023 for fuel and travel; CEA India 2023 for electricity.

**Why:**
- DEFRA (UK government) publishes the most widely used emissions factor dataset, updated annually. Used by most Indian ESG reporting frameworks as a secondary reference.
- CEA (Central Electricity Authority, India) publishes the India-specific grid emission factor annually. 0.716 kg CO₂e/kWh for 2022-23 (the most recent published value at time of writing).
- Market-based factors (RECs, PPAs) are not handled — we use location-based factors only.

**What I'd ask the PM:**
- Are they reporting under GHG Protocol, BRSR (SEBI), or both? Market-based vs location-based distinction matters for Scope 2.
- Which year's factors should be used? If they're reporting FY2023-24, should we use FY23-24 CEA factors?
