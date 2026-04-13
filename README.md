# ImageGen Local

A local AI image generation tool for product photography.  
Generates lifestyle / model images from product data using Google Gemini, with a review & approval workflow.

---

## What It Does

1. **Import** product data from `backend/data/products.xlsx`
2. **Generate** AI images using Gemini (or mock images for testing)
3. **Review** generated images in a browser UI
4. **Approve** or reject images — approved images are stored locally

---

## Stack

| Layer    | Technology                            |
|----------|---------------------------------------|
| Backend  | FastAPI + SQLAlchemy (async)          |
| Database | SQLite (file: `backend/imagegen.db`) |
| Auth     | Local JWT (username + password)       |
| Storage  | Local folder (`backend/local-images/`)|
| AI       | Google Gemini 2.5 Flash (or mock)     |
| Frontend | Vanilla JS + Vite                     |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) Google Cloud service account with Gemini API access

---

## Setup

### 1. Clone and configure

```bash
git clone <repo-url>
cd ImageGen_General_Local
```

The `.env` file is already included with safe local defaults. Edit it to change credentials or enable Gemini.

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MODE` | `mock` | `mock` = placeholder images, `gemini` = real Gemini |
| `DEV_ADMIN_EMAIL` | `admin@example.com` | Admin login |
| `DEV_ADMIN_PASSWORD` | `admin123` | Admin password |
| `DEV_EDITOR_EMAIL` | `editor@example.com` | Editor login |
| `DEV_EDITOR_PASSWORD` | `editor123` | Editor password |

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The database (`imagegen.db`) and image directories are created automatically on first startup.  
Two default users are seeded:

| Email | Password | Role |
|-------|----------|------|
| admin@example.com | admin123 | Admin |
| editor@example.com | editor123 | Editor |

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Load Products

### Option A — Via the Admin UI (recommended)

1. Place your Excel file at `backend/data/products.xlsx`
2. Log in as Admin → go to **Admin → Dev Tools**
3. Click **Import Excel Data**

### Option B — Via command line

```bash
cd backend
python import_excel.py
# or specify a custom path:
python import_excel.py path/to/yourfile.xlsx
```

The import is **idempotent** — running it multiple times is safe, it skips existing SKUs.

### Expected Excel columns

| Column | Field |
|--------|-------|
| `<ID>` | SKU ID |
| `<Parent ID>` | Groups sibling SKUs |
| `Markkinointinimi` | Marketing name |
| `Tuotekuvaus` | Description |
| `Materiaali` | Material |
| `Avainsanat` | Keywords |
| `SeasonName` | Season |
| `Campaigns Linked` | Campaign |
| `Väri` | Colour |
| `Koko` | Size |
| `DC B&M Stock Balance` | DC stock level |
| `Helsinki DS Stock Balance` | Helsinki stock level |
| `Brand` | Brand name |
| `<Retail Category [Node] Path>` | Category hierarchy |
| `Image1–5 Path` | Original image URLs |

---

## Using Gemini (Real AI)

1. Create a Google Cloud service account with Vertex AI / Gemini API access
2. Download the JSON key, save it as `backend/service-account.json`
3. Update `.env`:

```env
AI_MODE=gemini
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
GOOGLE_PROJECT_ID=your-gcp-project-id
```

4. Restart the backend

---

## Workflow

```
Import Excel → PENDING_AI
     ↓
Generate Image (Gemini or mock) → AI_READY
     ↓
Review images in the UI
     ↓
Approve → APPROVED    or    Reject (removes image)
     ↓
(optional) Recall approved image → back to AI_READY
```

---

## API Reference

Swagger UI: http://localhost:8000/docs

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Login → JWT |
| `GET`  | `/api/products` | List products (paginated, filterable) |
| `POST` | `/api/products/{sku}/regenerate` | Trigger AI generation |
| `POST` | `/api/products/{sku}/approve` | Approve image(s) |
| `POST` | `/api/products/{sku}/recall` | Recall an approved image |
| `POST` | `/api/admin/import-excel` | Import products.xlsx |
| `GET`  | `/health` | Health check |

---

## Project Structure

```
ImageGen_General_Local/
├── .env                        # Local environment config
├── backend/
│   ├── app/
│   │   ├── config.py           # Settings (reads .env)
│   │   ├── database.py         # SQLite async engine
│   │   ├── main.py             # FastAPI app
│   │   ├── models/             # SQLAlchemy models
│   │   ├── routers/            # API endpoints
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Business logic (AI, storage, audit)
│   │   └── middleware/         # Local JWT auth
│   ├── data/
│   │   └── products.xlsx       # Place your product Excel file here
│   ├── local-images/           # Generated images (auto-created)
│   ├── import_excel.py         # Excel import script
│   ├── requirements.txt
│   └── service-account.json    # Google service account (Gemini only)
└── frontend/
    ├── js/
    │   ├── api.js              # Backend API calls
    │   ├── auth.js             # JWT token storage
    │   └── pages/             # Page components
    ├── index.html
    └── vite.config.js
```

---

## Troubleshooting

**Backend won't start**
- Check Python version: `python --version` (need 3.11+)
- Activate the virtual environment: `source .venv/bin/activate`
- Run `pip install -r requirements.txt`

**"No products found" after import**
- Verify your Excel has the expected column headers (see table above)
- Check terminal output for error messages
- Run `python import_excel.py` directly for more detail

**Gemini images not generating**
- Set `AI_MODE=mock` first to verify the rest of the flow works
- Check `GOOGLE_SERVICE_ACCOUNT_FILE` points to a valid JSON key file
- Ensure your GCP project has the Gemini API enabled

**Login fails**
- Default credentials: `admin@example.com` / `admin123`
- Users are created on first backend startup — check terminal output
