# BlurTrace

A student case-study project exploring a privacy-first image blurring system with database-backed traceability.

> **Note:** This is a local demo built for a Data Science case study — not a production system. It does not handle real sensitive images, and several security-related features (auth, encryption) are intentionally out of scope. See [Scope & Limitations](#scope--limitations) below.

## The problem

Inappropriate or privacy-violating images are frequently shared on social media without the consent of the people in them, causing real harm — especially to children and other vulnerable individuals. BlurTrace explores a system that lets someone blur a sensitive image before sharing it, while still allowing an authorized process to trace that blurred image back to its original source later if needed.

## Core concept

Blurring is a one-way, destructive transformation — pixel information is genuinely discarded, so an original image cannot be mathematically reconstructed from a blurred one. Instead of attempting to reverse a blur, BlurTrace:

1. Blurs an image (Gaussian blur or pixelation).
2. Computes a hash of the blurred result's **pixel content**.
3. Stores the original and blurred image together in a database, keyed by that hash.
4. Later, an uploaded blurred image is hashed the same way and looked up by that key — a match returns the original.

This is a **database lookup/pairing mechanism, not image reconstruction**, and it only recognizes blurred images that BlurTrace itself produced.

## Features

- **Convert to Blur** — upload an image (drag & drop, browse, or paste with Ctrl+V), choose Gaussian blur or pixelation, adjust intensity with a live side-by-side preview, then Save (download) or Copy (clipboard) — both store the pair in the database.
- **Find the Original** — upload a blurred image to check whether BlurTrace has a matching original on record.
- Pixel-based exact hashing, so the match survives lossless re-encoding (e.g. clipboard round-trips), while remaining a true exact-match system (no fuzzy/perceptual matching).

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL (via psycopg2) |
| Image processing | OpenCV (`opencv-python-headless`) |
| Frontend | Plain HTML / CSS / JS (served as static files by FastAPI) |

## Project structure

```
BlurTrace/
├── backend/
│   ├── main.py            # FastAPI app: /api/process, /api/store, /api/find
│   ├── db.py               # Database connection, table creation, queries
│   ├── algorithms.py        # Gaussian blur, pixelation, pixel-based hashing
│   ├── requirements.txt
│   └── .env.example         # Copy to .env and fill in your local DB credentials
├── frontend/
│   ├── index.html           # Landing page
│   ├── convert.html         # Convert to Blur
│   ├── find.html            # Find the Original
│   ├── app.js               # Convert page logic (talks to the API)
│   └── style.css            # Shared dark theme styling
└── report/
    └── BlurTrace_Report.pdf # Case study summary report
```

## Getting started (local setup)

**Prerequisites:** Python 3.10+, PostgreSQL running locally.

1. **Clone the repo**
   ```bash
   git clone https://github.com/YOUR_USERNAME/blurtrace.git
   cd blurtrace/backend
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/Scripts/activate   # Git Bash on Windows
   # or: venv\Scripts\activate    # cmd/PowerShell
   # or: source venv/bin/activate # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your environment file**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` with your actual PostgreSQL host, port, database name, user, and password.

5. **Make sure PostgreSQL is running** and that the database named in `.env` (`DB_NAME`) exists.

6. **Run the server**
   ```bash
   python -m uvicorn main:app --reload
   ```
   The table is created automatically on startup if it doesn't already exist.

7. **Open the app** at [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/process` | POST | Blur an uploaded image. Returns blurred image (base64) + hash. Does not store anything. |
| `/api/store` | POST | Store an (original, blurred) pair, keyed by hash. Returns `stored` or `already_stored`. |
| `/api/find` | POST | Look up the original matching an uploaded blurred image by hash. 404 if no match. |

## Scope & limitations

The following are **intentional design decisions** for this case study, not oversights:

- **No encryption** — images are stored as plain bytes in PostgreSQL.
- **No authentication** — anyone running the app locally can store or look up any pair.
- **Single table design** — one `image_pairs` table, not normalized.
- **Exact-match hashing only** — matches are based on exact pixel content, not perceptual similarity. A lossy re-compression (e.g. saving as a low-quality JPEG) will still fail to match.
- **Closed-loop system** — only recognizes blurred images that BlurTrace itself produced; it cannot trace images blurred by other tools or platforms.

See `report/BlurTrace_Report.pdf` for the full write-up, including the debugging process behind these decisions.

## License

Student case-study project — for educational purposes.