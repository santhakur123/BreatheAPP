# SOURCES.md — Real-World Format Research

## Source 1: SAP Fuel & Procurement Data

### What I researched
SAP's Materials Management (MM) module tracks goods movements through the `MKPF` (header) and `MSEG` (line items) tables. Sustainability teams typically export from transaction SE16 or via a custom ABAP report.

Key fields I researched and modelled:
- `BELNR`: Material document number — unique within a SAP client, our `source_row_id`
- `BUDAT`: Posting date in YYYYMMDD format — SAP's internal date representation
- `WERKS`: Plant code — 4 characters, meaningless without a lookup table (SAP stores "IN01" not "Mumbai")
- `MAKTX`: Material description — stored in the language of the SAP system locale; German SAP systems export "Dieselkraftstoff" not "Diesel"
- `MEINS`: Base unit of measure — SAP internal codes, not SI units. "L" = litre, "GAL" = US gallon, "M3" = cubic metre, "TO" = metric tonne
- `BWART`: Movement type — 201 is "goods issue to cost centre" (actual consumption), 261 is "goods issue to production order"

### What the data actually looks like
SAP exports from SE16 produce a tab-separated file with a BOM (byte-order mark) at the start, which causes Python's `csv` module to prepend the BOM to the first column name. We handle this with `utf-8-sig` encoding.

Column headers vary by SAP system locale:
- English SAP: `Posting Date`, `Plant`, `Material Description`
- German SAP: `Buchungsdatum`, `Werk`, `Materialbezeichnung`
- SAP GUI export sometimes uses the technical field names: `BUDAT`, `WERKS`, `MAKTX`

Our parser handles all three via a header normalisation map.

### Why our sample data looks the way it does
- Mix of English and German material descriptions (realistic for a multinational)
- Dates in YYYYMMDD format (SAP default)
- Plant codes IN01/IN02/IN03/DE01/US01 (realistic 4-char codes)
- One outlier row with 150,000L diesel (row 7) — intentionally suspicious to test flagging
- One US plant with gallons (row 9) — tests unit conversion

### What would break in real deployment
- Movement type filtering: we ingest all rows. A real export should filter to BWART 201/261. Otherwise inter-plant transfers (BWART 301) inflate fuel consumption.
- Plant lookup: our `PLANT_LOOKUP` dict has 5 plants. A real client has hundreds.
- Period alignment: SAP posts by "posting date" not "service period." A fuel delivery posted on Jan 2 for December consumption will show in January.
- Large exports: 50,000-row MM export at ~200 bytes/row is 10MB — fine for our sync parser, would need Celery for anything larger.

---

## Source 2: Utility Data (Electricity)

### What I researched
Indian state DISCOMs (Distribution Companies) each have their own consumer portal. I specifically looked at:
- **BESCOM** (Bangalore Electricity Supply Company) — consumer portal exports a CSV with `Reading Date`, `Units Consumed`, `Amount`
- **MSEDCL** (Maharashtra State Electricity Distribution Co.) — similar portal, slightly different column names
- **Green Button Data** (US/UK standard) — XML format used by utilities that support ESPI standard

I chose CSV because Green Button XML is not used by Indian DISCOMs, and our client appears India-based (INR currency in SAP data).

Key complications I researched:
- **kVAh vs kWh**: Many Indian commercial/industrial consumers are billed in kVAh (apparent energy) not kWh (real energy). kVAh includes reactive power. Converting to kWh requires the power factor (typically 0.9–0.95 for commercial buildings). Without the power factor, you can't compute accurate CO₂e.
- **ToD (Time of Day) tariffs**: HT consumers pay different rates for peak (6am–10pm) and off-peak hours. Some BESCOM exports split into "Peak Units" and "Off-Peak Units". We store both but use total consumption for emission calculation.
- **Billing period alignment**: BESCOM billing cycles run 15th-to-15th, not month-to-month. A January report will show a billing period of Dec 15 – Jan 14. We normalise to the reading date.

### Why our sample data looks the way it does
- Two meters per account for Koramangala (realistic: Block A and Block B on separate meters)
- One kVAh meter (Mumbai Warehouse) — tests the power factor flag
- One MWh export (Mumbai Processing Unit) — tests the MWh→kWh conversion
- One row with 620,000 kWh (Manufacturing Plant) — just within realistic range for a large plant (~860kW average load), tests that it doesn't get incorrectly flagged

### What would break in real deployment
- Column name variation: BESCOM and MSEDCL have different headers. Our HEADER_ALIASES map covers common variants but would need expansion.
- PDF bills: Many facilities teams receive PDF bills, not portal CSV exports. PDF parsing is not implemented.
- Multi-site aggregation: A large enterprise might have 200 meters across 15 sites. The current upload is one-file-one-batch; bulk upload is not implemented.

---

## Source 3: Corporate Travel (Flights, Hotels, Ground)

### What I researched
- **Navan** (formerly TripActions): Their expense/travel platform exposes a REST API. The `/trips` endpoint returns a JSON array of trip objects, each with a `segments` array of typed objects (flight, hotel, car). I modelled our JSON format on their documented response structure.
- **Concur** (SAP Concur): Their TripIt integration and Expense API also return nested JSON. Concur uses "itinerary" terminology; segments are called "items."
- **DEFRA 2023 emission factors**: I used DEFRA's published GHG conversion factors for company reporting:
  - Flights: 0.255 kg CO₂e per passenger-km (economy, including radiative forcing)
  - Business class: 0.766 kg CO₂e per passenger-km
  - Hotel stays: 31.2 kg CO₂e per room-night (UK average)
  - Car rental: 0.21 kg CO₂e per km

### Distance calculation for flights
When the source doesn't provide distance (which is common — Navan provides it, Concur often does not), we compute it via the haversine formula from IATA airport coordinates. Our airport database covers 19 major airports. In production this would use the OurAirports open dataset (~7,000 airports).

Haversine gives great-circle distance, not actual flight path. Actual routes are ~10–20% longer. We do not apply a routing factor — this is noted as a limitation.

### Why our sample data looks the way it does
- Trip 1 (Priya Sharma, BLR→DEL→BLR): Domestic India flight — short haul, economy, with hotel and ground transport. Tests the domestic classification and haversine calculation.
- Trip 2 (Rahul Menon, BLR→LHR→CDG→BLR): Multi-leg international trip in business class. Tests long-haul, business class factor (3× economy), multi-hotel stay, and multi-city itinerary.
- Trip 3 (Ananya Krishnan, BOM→BLR→BOM): Short domestic hop without hotel. Tests minimal trip structure.

### What would break in real deployment
- Airport codes not in our lookup: We cover 19 airports. A real deployment would need the full OurAirports database (~7,000 airports). Unknown airport pairs currently return a parse error.
- Rail travel: Navan includes rail segments. We classify anything that's not flight or hotel as `ground_transport` and use a car emission factor. Rail's factor is ~0.04 kg CO₂e/km — significantly lower than car. This overestimates rail emissions.
- Radiative forcing: DEFRA's aviation factor includes radiative forcing (RF) at factor 1.9×. Some reporting frameworks use RF, others don't. We use the DEFRA factor that includes RF, which is the more conservative choice.
