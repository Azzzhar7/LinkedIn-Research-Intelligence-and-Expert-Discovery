# LinkedIn Research Intelligence & Expert Discovery Platform

A localhost Streamlit application for building a clean research/contact dataset from an official LinkedIn Connections CSV export, manually reviewing profile information, calculating career experience, finding relevant experts, and exporting results.

## Scope and safe operating model

The app does **not** automate bulk collection, scrolling, or extraction from logged-in LinkedIn pages. LinkedIn controls access to its site and data; use its official data-export tools and review profile information only where you have permission. The browser-assisted option simply opens the Connections/Profile URLs for you — you enter any profile information you are entitled to use into the local app.

All imported data, calculated scores, and exports are stored locally in `data/research.db` and `exports/`.

## Quick start (Windows)

1. Open PowerShell in this folder.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies and start the app:

   ```powershell
   pip install -r requirements.txt
   streamlit run streamlit_app.py
   ```

4. In the app: import your Connections CSV → enter research keywords in **Quick research run** → score all records with a visible progress bar → manually enrich only the shortlist if needed → export Excel/CSV.

### Job controls

Scoring runs in a local background process. The sidebar provides **Start**, **Pause**, **Resume**, **Stop**, **Re-run last query**, an **Auto-run after next CSV import** option, and live auto-refresh. Pause/Stop take effect at the next saved batch (at most 25 profiles).

## Workflow

```text
Official connection CSV
        ↓
Cleaning: normalize fields, validate URLs, de-duplicate
        ↓
SQLite queue (resumable; reviewed/pending profile state)
        ↓
Researcher-directed browser review and role entry
        ↓
Experience aggregation + seniority detection
        ↓
Local relevance scoring + expert classification
        ↓
Excel/CSV master data, relevant experts, research summary
```

## Architecture

| Component | Purpose |
|---|---|
| `streamlit_app.py` | UI, dashboard, import/review/score/export controls |
| `app/database.py` | SQLite schema, runs, checkpoints and event logging |
| `app/cleaning.py` | Connection-file normalization, URL validation and de-duplication |
| `app/profiles.py` | Manual review persistence, aggregate full-career calculation |
| `app/scoring.py` | Local TF-IDF semantic/keyword matching and expert flags |
| `app/exporting.py` | CSV + Excel master dataset, relevant-expert sheet and summary |
| `app/browser_assist.py` | Playwright-oriented browser-review integration boundary (no scraping) |

## Database schema

- `profiles`: imported identity data, manual enrichment, full career history, calculated totals and status.
- `relevance`: query-specific scores, matched terms, classifications and validation priority.
- `runs`: processing status/current item/progress counters, enabling status display and resumption.
- `events`: local audit and error log for each run.

## Current classification rules

- **Potential validator:** at least 5 years of aggregated experience, relevance score at least 70, and an academic or industry indicator.
- **Priority:** High requires strong relevance (85+) and 8+ years; otherwise eligible profiles are Medium.
- **Expert flags:** transparent keyword indicators for academic, industry, security, and architecture expertise.

## Implementation roadmap

1. Use the current workflow for a small pilot and tune thresholds/keywords.
2. Add approved-data connectors (for example, a licensed enrichment provider) only after verifying permissions and terms.
3. Add a controlled review-assignment feature for multiple researchers.
4. Add encrypted-at-rest storage and role-based access if the data will be shared.
