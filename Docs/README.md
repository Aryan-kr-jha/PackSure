# PackSure — AI-Powered Legal Metrology Compliance Verification System

PackSure is an AI-assisted automated compliance verification and screening platform designed for the **Legal Metrology Division, Department of Consumer Affairs (Government of India)** under the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR, 2011)** and E-Commerce Compliance mandates.

It performs statutory inspection on physical packaged commodity labels (via multi-engine OCR & Vision AI) and digital e-commerce listings (via automated URL scraping & HTML parsing) to detect non-compliance, generate official violation reports, and export tamper-evident inspection PDFs.

> [!IMPORTANT]
> **Image Quality & OCR Accuracy Notice**:
> For optimal extraction accuracy, upload **high-resolution, clear, well-lit, and straight (un-skewed)** label images with minimal blur or glare. The local OCR engine currently delivers approximately **~70% baseline extraction accuracy** on raw packaging captures; degraded, heavily tilted, or blurry images will reduce accuracy and should be rescanned for reliable statutory verification.

> [!NOTE]
> **Processing Time Notice**:
> Please note that **new image extraction can take up to 4 minutes** on un-cached images while the multi-stage OCR, text parsing, Vision AI, and PCR 2011 rule-comparison pipeline processes the label. **Development is actively in progress to optimize this pipeline and make it significantly faster.**
> *(Previously verified demo packages and cached scans return instant sub-second results via exact SHA-256 fingerprint matching).*

---

## 📋 Table of Contents
- [Overview & Architecture](#overview--architecture)
- [Key Features](#key-features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Environment Configuration](#environment-configuration)
- [Running the Server](#running-the-server)
  - [Method 1: Local Development (Recommended)](#method-1-local-development-recommended)
  - [Method 2: Docker Container](#method-2-docker-container)
- [Default Demo Credentials](#default-demo-credentials)
- [API Endpoints Reference](#api-endpoints-reference)
- [Project Directory Structure](#project-directory-structure)
- [Testing & Quality Assurance](#testing--quality-assurance)

---

## 🏛️ Overview & Architecture

The PackSure system is engineered as an integrated FastAPI backend coupled with a vanilla responsive UI:
1. **Frontend**: Static Web application in `Frontend/` served directly by FastAPI at `/` or accessed independently.
2. **Backend**: FastAPI RESTful service in `Backend/` providing inspection endpoints, analytical dashboards, OCR processing pipelines, and PDF report generators.
3. **Computer Vision & Extraction**:
   - Primary: PaddleOCR and EasyOCR engines (`Backend/ocr/`).
   - Fallback & Enrichment: Google Gemini Vision AI (`Backend/services/vision_ai.py`).
   - Rule Engine: 10 statutory declaration checkers according to Legal Metrology Rules (`Backend/declarations.py`, `Backend/extraction.py`).
4. **Database & Storage**:
   - Supabase PostgreSQL (or fallback in-memory/demo repository) with migration schemas in `Supabase/migrations/`.
   - File storage for packaging label image uploads in `Backend/uploads/`.

---

## ✨ Key Features

- **Mandatory 10-Declaration Verification**:
  1. Manufacturer / Packer / Importer Name & Address (with PIN verification)
  2. Country of Origin
  3. Common or Generic Name of Commodity
  4. Net Quantity (weight, volume, measure, or numerical count)
  5. Maximum Retail Price (MRP inclusive of all taxes)
  6. Unit Sale Price (USP) Calculation and Mathematical Accuracy Check
  7. Month and Year of Manufacture / Packing / Import
  8. Expiry / Best Before Date (for perishable items)
  9. Sizes and Dimensions of the Commodity (where applicable)
  10. Consumer Care Details (Name, Address, Telephone Number, and Email)
- **Mathematical Validation of USP**: Automatically re-calculates whether `USP = MRP / Net Quantity` within statutory tolerance limits.
- **E-Commerce URL Compliance Checker**: Extracts product metadata from e-commerce product pages (e.g., Blinkit, Amazon, Flipkart, Zepto) and flags missing mandatory declarations before consumers purchase.
- **Statutory Inspection PDF Generation**: Produces printable regulatory inspection violation reports and notices (`Backend/reports/pdf.py`).
- **Inspector Analytics Dashboard**: Aggregates pass/fail compliance trends, common violation categories, and inspection history.

---

## ⚙️ Prerequisites

- **Operating System**: Windows 10/11, macOS, or Linux (Ubuntu 20.04+ recommended for servers)
- **Python**: Version `3.10`, `3.11`, or `3.12`
- **System Dependencies (for Linux / Docker)**:
  - OpenCV & OCR system dependencies: `libgl1`, `libglx-mesa0`, `libglib2.0-0`, `libsm6`, `libxext6`, `libgomp1`, `ffmpeg`

---

## 🚀 Installation & Setup

### 1. Clone or Open the Repository
Ensure you are at the root directory of the project:
```bash
cd PackSure
```

### 2. Set Up a Python Virtual Environment
**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔐 Environment Configuration

Create a `.env` file in the root directory based on `.env.example`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

### Configuration Variables (`.env`)

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `APP_NAME` | No | `PackSure AI` | Application branding name |
| `ENVIRONMENT` | No | `development` | `development` or `production` |
| `SUPABASE_URL` | Optional | `""` | Supabase instance URL (for persistent scan history) |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | `""` | Supabase service role secret key |
| `UPLOAD_DIR` | No | `Backend/uploads` | Path for saving uploaded package images |
| `MAX_UPLOAD_BYTES` | No | `10485760` (10 MB) | Max file upload size limit |
| `CORS_ORIGINS` | No | `*` | Allowed CORS origins (comma-separated) |
| `COMPLIANCE_PRICE_TOLERANCE` | No | `0.05` | Permissible deviation tolerance for USP verification |
| `VISION_AI_ENABLED` | Optional | `false` | Enable Gemini Vision fallback for complex packaging |
| `VISION_AI_PROVIDER` | Optional | `gemini` | Vision AI service provider |
| `VISION_AI_MODEL` | Optional | `gemini-2.5-flash` | Gemini Vision model variant |
| `GEMINI_API_KEY` | Optional | `""` | Google Gemini API Key |

> **Note**: If Supabase credentials are left empty, the application automatically falls back to an in-memory repository with pre-cached demo inspections.

---

## 🖥️ Running the Server

### Method 1: Local Development (Recommended)

Run the server with Uvicorn from the project root using `--app-dir Backend`:

**From Project Root (PowerShell / Command Prompt):**
```powershell
python -m uvicorn app:app --app-dir Backend --host 0.0.0.0 --port 8000 --reload
```

**Or directly inside the `Backend` directory:**
```powershell
cd Backend
python app.py
```

Once running:
- **Web UI & Officer Portal**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Method 2: Docker Container

You can run the entire system inside a Docker container:

```bash
# Build the Docker image
docker build -t packsure:latest .

# Run the container mapping port 8080 to 8080
docker run -p 8080:8080 --env-file .env packsure:latest
```
Access the application at [http://localhost:8080](http://localhost:8080).

---

## 👤 Default Demo Credentials

For demonstration, testing, and evaluation:

- **Officer Login ID**: `officer.demo`
- **Officer Password**: `Demo@123`

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server health check and database status |
| `POST` | `/api/scan` | Upload a JPEG package image for OCR analysis and compliance check |
| `POST` | `/api/scan-url` | Scrapes an e-commerce product URL (`{"url": "..."}`) and checks online compliance |
| `GET` | `/api/scans` | Paginated list of historical inspection scans |
| `GET` | `/api/scans/{scan_id}` | Detailed inspection record by scan ID |
| `GET/POST` | `/api/reports/pdf?scan_id={id}` | Download a statutory violation PDF report for the given scan ID |
| `GET` | `/api/analytics/dashboard` | Aggregated compliance metrics and charts for inspector officers |

---

## 📁 Project Directory Structure

```text
PackSure/
├── Backend/
│   ├── api/
│   │   └── routes.py              # REST API route handlers
│   ├── core/
│   │   └── config.py              # Application settings and environment variables
│   ├── db/
│   │   └── repository.py          # Supabase and fallback storage persistence layer
│   ├── ocr/
│   │   └── ocr_engine.py          # PaddleOCR / EasyOCR text recognition engine
│   ├── reports/
│   │   └── pdf.py                 # ReportLab statutory inspection PDF generator
│   ├── services/
│   │   ├── analyzer.py            # Package label extraction and compliance pipeline
│   │   ├── demo_cache.py          # Sample inspection fixtures and demo data
│   │   ├── digital_compliance.py  # E-commerce listing verification service
│   │   ├── vision_ai.py           # Gemini Vision AI integration
│   │   └── web_scraper.py         # Web scraping utility for product URLs
│   ├── uploads/                   # Stored label image uploads
│   ├── declarations.py            # Legal Metrology mandatory 10-declaration rules
│   ├── extraction.py              # Regex and pattern extraction for MRP, USP, & Net Qty
│   └── app.py                     # FastAPI application entrypoint and static mount
├── Docs/
│   └── README.md                  # Detailed documentation and startup guide
├── Frontend/
│   ├── index.html                 # Officer Portal single-page application
│   ├── styles.css                 # Clean, statutory UI styles
│   └── app.js                     # Frontend state management and API communication
├── Supabase/
│   └── migrations/
│       └── 001_initial_schema.sql # Database schema for scans and compliance tables
├── data/                          # Sample packaging images for testing
├── tests/                         # Automated unit and integration test suites
├── Dockerfile                     # Production container definition
├── requirements.txt               # Python package dependencies
├── nixpacks.toml                  # Nixpacks deployment configuration
└── vercel.json                    # Vercel deployment configuration
```

---

## 🧪 Testing & Quality Assurance

Run the test suite using `pytest`:

```bash
pytest
```

To run a specific test file:
```bash
pytest tests/test_declarations.py
```
