# Breathe ESG — Emissions Ingestion & Review Platform

A Django REST + React prototype for ingesting, normalising, and reviewing emissions data from three source types: SAP flat files, utility portal CSVs, and corporate travel JSON exports.

## Demo Credentials

| Username | Password | Role |
|---|---|---|
| analyst | breathe2024 | Analyst |
| admin | breathe2024 | Admin |

---

## Local Development

### Prerequisites
- Python 3.11+
- Node 18+
- PostgreSQL 15+

### Backend

```bash
cd backend

# Create and activate virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create the database
createdb breathe_esg

# Run migrations
python manage.py migrate

# Seed demo data (creates org, users, and sample records for all 3 sources)
python manage.py seed_demo_data

# Start dev server
python manage.py runserver
```

Backend runs at http://localhost:8000

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173

---

## Project Structure

```
breathe-esg/
├── backend/
│   ├── breathe_esg/          # Django settings, URLs, WSGI
│   ├── apps/
│   │   ├── accounts/         # Auth: login, logout, /me
│   │   ├── emissions/        # Core models, views, serializers
│   │   │   ├── models.py     # Organisation, IngestionBatch, EmissionRecord, EditLog
│   │   │   ├── views.py      # Dashboard, record CRUD, review actions
│   │   │   └── serializers.py
│   │   ├── ingestion/        # Upload endpoints + parsers
│   │   │   ├── views.py      # /ingest/sap/, /ingest/utility/, /ingest/travel/
│   │   │   └── parsers/
│   │   │       ├── sap_parser.py      # SAP flat file → EmissionRecord
│   │   │       ├── utility_parser.py  # Utility CSV → EmissionRecord
│   │   │       └── travel_parser.py   # Travel JSON → EmissionRecord
│   │   └── audit/            # Placeholder for audit export
│   └── requirements.txt
├── frontend/
│   └── src/App.jsx           # Single-file React app
├── docs/
│   ├── MODEL.md              # Data model & rationale
│   ├── DECISIONS.md          # Every ambiguity resolved
│   ├── TRADEOFFS.md          # Three things not built
│   └── SOURCES.md            # Real-world format research
└── render.yaml               # Render deployment config
```

---

## API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login/` | Returns token |
| POST | `/api/auth/logout/` | Invalidates token |
| GET | `/api/auth/me/` | Current user + org |

### Ingestion
| Method | Path | Description |
|---|---|---|
| POST | `/api/ingestion/sap/` | Upload SAP flat file (multipart) |
| POST | `/api/ingestion/utility/` | Upload utility CSV (multipart) |
| POST | `/api/ingestion/travel/` | Upload travel JSON (multipart or JSON body) |

### Emissions
| Method | Path | Description |
|---|---|---|
| GET | `/api/emissions/dashboard/` | Summary totals by scope + review status |
| GET | `/api/emissions/records/` | Paginated records (filterable) |
| PATCH | `/api/emissions/records/{id}/` | Edit a record (logged) |
| POST | `/api/emissions/records/{id}/review/` | Approve / reject / flag |
| POST | `/api/emissions/records/{id}/lock/` | Lock approved record for audit |
| POST | `/api/emissions/records/bulk_approve/` | Bulk approve by ID list |
| GET | `/api/emissions/batches/` | Ingestion history |

### Query Parameters for `/api/emissions/records/`
- `scope=1|2|3`
- `review_status=pending|approved|rejected|flagged`
- `is_flagged=true|false`
- `batch={batch_uuid}`
- `date_from=YYYY-MM-DD`
- `date_to=YYYY-MM-DD`

---

## Deployment on Render

1. Push to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your repo
4. Render reads `render.yaml` and creates: PostgreSQL DB, Django backend, React static site
5. Set `VITE_API_URL` in the frontend service to your backend's Render URL

**Important:** After first deploy, if `seed_demo_data` didn't run automatically, trigger it manually:
```
Render Dashboard → Backend service → Shell → python manage.py seed_demo_data
```

---

## Sample Data Files

The `seed_demo_data` management command automatically seeds all three sources. To test manual uploads:

**SAP flat file** — Create a `.txt` file with tab-separated columns:
```
BELNR	BUDAT	WERKS	MAKTX	MENGE	MEINS	LIFNR	KOSTL	DMBTR	WAERS
5000099001	20240401	IN01	Diesel Kraftstoff	3000.000	L	VEND001	CC-OPS	210000	INR
```

**Utility CSV** — Create a `.csv` with:
```
Account Number,Meter Number,Reading Date,Units Consumed,Unit,Amount,Currency,Location,Tariff Code
KEB-10099,MTR-001,01/04/2024,42000,kWh,294000,INR,New Site,HT-2
```

**Travel JSON** — POST body or `.json` file:
```json
{"trips": [{"id": "T001", "traveller": "Test User", "department": "Eng", "segments": [{"type": "flight", "origin": "BLR", "destination": "DEL", "departure_date": "2024-04-01", "cabin": "economy", "passengers": 1}]}]}
```
