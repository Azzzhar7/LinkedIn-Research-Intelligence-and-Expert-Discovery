# Developer Guide

## What this application does

This is a local Streamlit research workspace. It imports an official LinkedIn Connections CSV export, cleans and de-duplicates it, lets a researcher review permitted profile information, calculates aggregate career experience, scores relevance against a research query, and exports Excel/CSV files.

It deliberately does not automate bulk LinkedIn extraction, page scrolling, or logged-in session scraping. The browser-assisted path opens URLs for researcher-directed review only.

## Prerequisites

- Windows 10/11
- Python 3.10 or newer (`py --version`)
- PowerShell
- An official LinkedIn Connections CSV export for testing

## Install and run

From the project root, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Streamlit will print a localhost URL, normally `http://localhost:8501`. Open it in a browser.

To stop the application, return to PowerShell and press `Ctrl+C`.

### If PowerShell blocks virtual-environment activation

Use this once in the current terminal, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## First local test

1. Download an official Connections CSV from LinkedIn.
2. Open **1. Import & clean** and upload it.
3. Confirm the valid/unique count after cleaning.
4. In **2. Review queue**, choose one profile, enter its permitted information and at least one career role.
5. In **3. Research matching**, enter a query such as `DevSecOps, software architecture, secure scrum`.
6. In **4. Export**, create the CSV and Excel files.

### Background job controls

The sidebar starts scoring in a separate local Python process, so the UI remains usable. It has Start, Pause, Resume, Stop, Re-run last query, and Auto-run after next CSV import controls. A control request is checked after each batch of up to 25 profiles; it is therefore not necessarily instantaneous.

The SQLite database is created automatically at `data/research.db`; generated files are saved in `exports/`.

## Project layout

```text
linkedin-research-platform/
├── streamlit_app.py        # User interface and workflow orchestration
├── requirements.txt        # Runtime packages
├── app/
│   ├── database.py         # SQLite schema, run tracking, events
│   ├── cleaning.py         # CSV normalization and URL validation
│   ├── profiles.py         # Profile review and career aggregation
│   ├── scoring.py          # Local relevance and expert classification
│   ├── exporting.py        # Excel / CSV exports
│   ├── browser_assist.py   # Browser-review integration boundary
│   └── config.py           # Local folders and database path
├── data/                   # Local SQLite database (ignored by Git)
├── logs/                   # Reserved for local logs
└── exports/                # Generated research files (ignored by Git)
```

## Data model

| Table | Purpose |
|---|---|
| `profiles` | Source data, reviewed fields, experience JSON, calculated career metrics, status |
| `relevance` | Query-specific relevance score, matched terms, classifications, priority |
| `runs` | Operation status and progress counters for import/scoring jobs |
| `events` | Local activity/audit messages |

`linkedin_url` is unique. Re-importing a CSV updates the imported fields for the same URL without creating a duplicate profile.

## Development workflow

1. Activate the virtual environment.
2. Start the UI with `streamlit run streamlit_app.py`.
3. Make a small focused change in `app/` or `streamlit_app.py`.
4. Streamlit automatically reloads after a save.
5. Test with a small CSV before a larger import.
6. Check the dashboard and exported workbook after each workflow change.

### Run basic checks

```powershell
python -m compileall -q app streamlit_app.py
```

### Reset only local test data

Stop Streamlit first. Then delete `data/research.db` manually from File Explorer. The next app run creates a clean database. This permanently removes locally imported/reviewed data, so take an export first if needed.

## Extending the app

### Add CSV aliases

Update `URL_COLUMNS` or `first_existing()` in `app/cleaning.py` if an official export uses a different column name.

### Adjust relevance scoring

`app/scoring.py` contains the local TF-IDF cosine scoring and exact-keyword boost. Adjust these values to tune strictness:

- Relevant threshold: `score >= 60`
- Potential-validator threshold: `5+ years`, score `>= 70`, plus academic or industry flag
- High priority: score `>= 85` and `8+ years`

### Add expert indicators

Add terms in `classify()` in `app/scoring.py`. Keep each indicator explainable and validate it against a small reviewed dataset before using it for participant selection.

### Add fields

Adding a field requires three coordinated edits:

1. Add a column in `profiles` or `relevance` in `app/database.py`.
2. Add UI input/display in `streamlit_app.py`.
3. Add persistence in `app/profiles.py` or `app/scoring.py`.

For an existing database, SQLite does not automatically add a changed schema column. During development, reset a test database, or add a deliberate migration using `ALTER TABLE`.

## Troubleshooting

| Issue | Resolution |
|---|---|
| `streamlit` is not recognized | Activate `.venv`, then run `python -m pip install -r requirements.txt`. |
| CSV import says no URL column | Ensure the file has `URL`, `LinkedIn URL`, `linkedin_url`, or `Profile URL`; otherwise add its alias in `app/cleaning.py`. |
| Excel export fails | Reinstall dependencies so `openpyxl` is present: `python -m pip install openpyxl`. |
| Port 8501 is busy | Run `streamlit run streamlit_app.py --server.port 8502`. |
| The app is using old data | Stop the app, confirm `data/research.db`, and either re-import or reset a non-production test database. |

## Privacy and operational guidance

- Keep the project folder and `data/research.db` on an access-controlled device.
- Export only fields necessary for your research purpose.
- Validate shortlists manually before contacting people or making research decisions.
- Do not add an automated browser collection routine without confirming you have a permitted data source and the necessary authority.
