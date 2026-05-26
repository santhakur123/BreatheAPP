# Breathe ESG — Emissions Ingestion & Review Platform
# THis is the live link  of render :https://breathe-esg-frontend-41r2.onrender.com/
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
│   ├── breathe_esg/          
│   ├── apps/
│   │   ├── accounts/         
│   │   ├── emissions/        
│   │   │   ├── models.py     
│   │   │   ├── views.py      
│   │   │   └── serializers.py
│   │   ├── ingestion/       
│   │   │   ├── views.py      
│   │   │   └── parsers/
│   │   │       ├── sap_parser.py      
│   │   │       ├── utility_parser.py  
│   │   │       └── travel_parser.py   
│   │   └── audit/            
│   └── requirements.txt
├── frontend/
│   └── src/App.jsx           
├── docs/
│   ├── MODEL.md              
│   ├── DECISIONS.md         
│   ├── TRADEOFFS.md          
│   └── SOURCES.md            
└── render.yaml              
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




