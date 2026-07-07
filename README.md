# BlurTrace

**A traceable image-blurring system — student case study.**

🔗 **Live Demo:** [https://blurtrace.onrender.com/](https://blurtrace.onrender.com/)
> Hosted on Render's free tier — the first load after inactivity may take 30-60 seconds to wake up. This is expected.

BlurTrace lets you blur a sensitive image before sharing it, while keeping a secure, database-backed way to trace that blurred image back to its original source later, if it's ever needed.

> Local demo project for a Data Science case study. Not intended for real sensitive images, and not a production system — see [Scope & Limitations](#scope--limitations) below.

---

## Table of Contents

- [BlurTrace](#blurtrace)
  - [Table of Contents](#table-of-contents)
  - [The Problem](#the-problem)
  - [Core Concept](#core-concept)
  - [How It Works (Mechanism)](#how-it-works-mechanism)
  - [Algorithms](#algorithms)
    - [1. Gaussian Blur](#1-gaussian-blur)
    - [2. Pixelation](#2-pixelation)
    - [3. SHA-256 Hashing (Pixel-Based)](#3-sha-256-hashing-pixel-based)
    - [Why Hashing At All?](#why-hashing-at-all)
  - [System Architecture](#system-architecture)
  - [Database](#database)
    - [Table Reference — What Each Column Means](#table-reference--what-each-column-means)
  - [API Endpoints](#api-endpoints)
  - [Web Demo — Pages](#web-demo--pages)
    - [1. Landing Page](#1-landing-page)
    - [2. Convert to Blur](#2-convert-to-blur)
    - [3. Find the Original](#3-find-the-original)
  - [Running the Project](#running-the-project)
  - [Scope \& Limitations](#scope--limitations)

---

## The Problem

Images shared without consent — on social media, messaging apps, or elsewhere — can cause lasting harm, especially to children and other vulnerable people. Once an image is out, it's effectively impossible to take back.

BlurTrace explores a middle ground: **blur an image before sharing it**, so the sensitive content is protected by default, while still keeping a way to **recover the original later** through an authorized lookup — for example, if a blurred image is found circulating and someone needs to verify or investigate its source.

---

## Core Concept

Blurring is a **one-way, destructive transformation**. Once pixel detail is averaged or discarded, the original image cannot be mathematically reconstructed from the blurred result alone — there is no algorithm that "un-blurs" an image back to its source.

So instead of trying to reverse a blur, BlurTrace does this:

1. Take an original image **X**.
2. Apply a blur algorithm to produce a blurred version **Y**.
3. Compute a hash of **Y**.
4. Store **X** and **Y** together in a database row, keyed by that hash, the moment **Y** is saved or copied for use.
5. Later, if someone uploads a file matching **Y**, the system looks up the row and returns **X**.

**This is a database lookup/pairing mechanism — not image reconstruction.** BlurTrace never reverses a blur; it recognizes an image it has already seen and hands back what it was paired with.

---

## How It Works (Mechanism)

```
 ┌─────────────┐      blur       ┌─────────────┐      hash       ┌──────────────┐
 │  Original X │ ───────────────▶│  Blurred Y  │ ───────────────▶│ hash(Y)      │
 └─────────────┘                 └─────────────┘                 └──────────────┘
                                                                          │
                                                     store (X, Y, hash(Y)) as one row
                                                                          ▼
                                                                 ┌──────────────────┐
                                                                 │   image_pairs     │
                                                                 │   database table  │
                                                                 └──────────────────┘
                                                                          ▲
                                        lookup by hash(uploaded file)     │
 ┌────────────────┐        hash        ┌──────────────┐                  │
 │ Uploaded image │ ──────────────────▶│ hash(upload) │──────────────────┘
 └────────────────┘                    └──────────────┘
        found → return X          not found → "no match" message
```

**Important constraint:** this system is a **closed loop**. It can only recognize a blurred image that BlurTrace itself produced and stored. A blurred image from any other tool or platform will correctly return "no match," since there's no stored pair to find.

---

## Algorithms

### 1. Gaussian Blur

Each pixel's new value is a weighted average of its neighboring pixels, with weights following a Gaussian (bell-curve) distribution — nearby pixels contribute more, distant ones less. This is a standard spatial convolution, with no randomness involved.

- **Intensity (1–10)** controls the blur kernel size: a larger kernel averages over a wider neighborhood, producing a stronger blur.

### 2. Pixelation

The image is downscaled to a much lower resolution, then scaled back up using nearest-neighbor interpolation. Each block in the enlarged image becomes one flat color, producing the blocky "mosaic" effect.

- **Intensity (1–10)** controls how small the downscale target is — a smaller target produces chunkier, more pixelated blocks.

Both algorithms are **lossy and one-directional**: information is genuinely discarded during blurring, which is exactly why there is no mathematical inverse — and exactly why BlurTrace uses a pairing/lookup mechanism instead of trying to reverse the blur.

### 3. SHA-256 Hashing (Pixel-Based)

SHA-256 produces a fixed-length, one-way fingerprint of input data: identical input always produces an identical hash, and any change to the input produces a completely different one.

BlurTrace hashes the **decoded pixel array** of the blurred image (not its raw file bytes). This matters because:

- Raw file bytes can differ even for visually identical images — for example, an image copied to the clipboard and pasted elsewhere may be re-encoded with different compression settings, producing different file bytes for the same pixels.
- Hashing pixel data instead makes the match survive this kind of **lossless** re-encoding, while still being genuinely exact — it's exact on pixel content rather than exact on file encoding.
- This does **not** make BlurTrace a fuzzy/perceptual matching system. A *lossy* re-compression (e.g. saving as a low-quality JPEG) still changes pixel values and will still fail to match — that broader case is intentionally out of scope.

### Why Hashing At All?

Since the database already stores full pixel data for both images, matching *could* technically be done by comparing an uploaded image's pixels directly against every stored blurred image — no hash required for correctness. So what does hashing actually buy us?

**Speed, not correctness.** A hash is always a fixed, short length — SHA-256 is always exactly 64 hex characters, whether the input is a tiny icon or a 20-megapixel photo. That fixed size matters for two reasons:

1. **Comparing is cheap.** Comparing two 64-character strings is nearly instant. Comparing two multi-megabyte images pixel-by-pixel is not.
2. **Databases can index it.** Postgres can build an index on `blurred_hash`, letting it jump almost straight to a matching row instead of scanning every row one by one. Raw binary blobs can't be indexed and searched the same way.

Without a hash, `/api/find` would need to pull out *every* stored blurred image, decode each one, and compare it pixel-by-pixel against the upload — a full scan that gets slower as more images are stored. With a hash, it's one indexed lookup: `WHERE blurred_hash = X`.

**Why only the blurred image is hashed — not the original:** a user only ever uploads a *blurred* image when using Find the Original; nobody searches by uploading the original, since they don't have it — that's the whole reason they need to trace it. So the blurred image is the only thing that ever needs to become a searchable key. The original is just the answer sitting in the row, returned once its paired blurred image's hash is matched.

**What a hash actually looks like:** it's not a smaller picture or a visual thing — it's a transformation of the image's pixel numbers into a fixed string of hex characters. Same input pixels always produce the exact same string; changing even one pixel produces a completely different one, and there's no way to work backward from the string to see what the image looked like.

```
[pixel data: e.g. 300 x 300 x 3 array of numbers]
              │
              ▼
        SHA-256 function
              │
              ▼
"9bedd25af033c4c6c788336b9607c29a4a18615db5549e9e65eb63af3..."
   (always exactly 64 characters, no matter the image size)
```

That string is exactly what appears in the `blurred_hash` column shown in the [Table Reference](#table-reference--what-each-column-means) above.

---

## System Architecture

| Layer | Technology | Role |
|---|---|---|
| Backend | Python, FastAPI | Exposes `/api/process`, `/api/store`, `/api/find` |
| Database | PostgreSQL (via psycopg2) | Single `image_pairs` table storing original + blurred bytes, keyed by hash |
| Image processing | OpenCV (`opencv-python-headless`) | Gaussian blur, pixelation, pixel-based hashing |
| Frontend | Plain HTML / CSS / JS | Three pages: Landing, Convert to Blur, Find the Original |

```
BlurTrace/
├── backend/
│   ├── main.py           # FastAPI app & endpoints
│   ├── db.py              # Database connection, table setup, store/find queries
│   ├── algorithms.py      # Gaussian blur, pixelation, pixel-based hashing
│   ├── requirements.txt
│   └── .env               # Local DB credentials (not committed)
└── frontend/
    ├── index.html          # Landing page
    ├── convert.html        # Convert to Blur page
    ├── find.html           # Find the Original page
    ├── app.js              # Convert page logic (upload, blur, save/copy)
    └── style.css           # Shared dark/blue theme
```

---

## Database

A single table, storing both images together as bytes, keyed by the blurred image's hash:

```sql
CREATE TABLE IF NOT EXISTS image_pairs (
    image_id        UUID PRIMARY KEY,
    original_img    BYTEA NOT NULL,
    blurred_img     BYTEA NOT NULL,
    blurred_hash    TEXT UNIQUE NOT NULL,
    blur_method     TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**Deliberate scope decisions** (see [Scope & Limitations](#scope--limitations)):
- Plain bytes, no encryption.
- Single table — not normalized into separate tables.
- `blurred_hash` is `UNIQUE`, so the same blurred output is never stored twice.

### Table Reference — What Each Column Means

| Column | Type | Meaning |
|---|---|---|
| `image_id` | UUID (Primary Key) | A unique, randomly generated ID for the row itself. Not derived from the image — just how the database tells pairs apart, and what gets returned to the frontend when a match is found. |
| `original_img` | BYTEA | The raw bytes of the original, unblurred image. |
| `blurred_img` | BYTEA | The raw bytes of the blurred image shown to the user. |
| `blurred_hash` | TEXT (Unique) | The SHA-256 hash of the blurred image's **decoded pixel data**. This is the actual lookup key — `/api/find` hashes an uploaded image the same way and searches this column for a match. Marked `UNIQUE` so the same blurred result is never stored twice. |
| `blur_method` | TEXT | Which algorithm produced this row's blurred image — `"gaussian"` or `"pixelate"`. Shown back to the user on a successful Find (e.g. "Matched a pair stored via pixelate"). |
| `created_at` | TIMESTAMP | When the row was inserted, set automatically. |

**Example rows** (as seen in pgAdmin — `original_img` and `blurred_img` are omitted here since they're raw binary data, not human-readable):

| image_id | blur_method | blurred_hash | created_at |
|---|---|---|---|
| `a1c9cd15-8f7d-42e3-...` | pixelate | `9bedd25af033c4c6c788336b9607c29a4a18615db5549...` | 2026-07-06 15:42:10 |
| `3720c34d-33c2-47be-...` | pixelate | `71a5f59d64770aff7823387e106cc967db6b2f3e94e7a...` | 2026-07-06 15:44:03 |
| `f49568cd-8594-4913-...` | pixelate | `7afa42ad62d8256ed74aa43e9b5486356d482d0aa25438...` | 2026-07-06 15:45:51 |
| `8403726f-8880-40f9-...` | gaussian | `ba898fa28367e21360202715050eb8682a5de9815f6a6...` | 2026-07-06 15:47:22 |
| `9f8d5a85-624b-42d6-...` | pixelate | `f249df202ccef2f38f6d4b437aed1d0c22f6d6d6327e75...` | 2026-07-06 15:48:09 |

Each row is one stored pair. The `blurred_hash` is what connects an uploaded blurred image back to its `original_img` — nothing more than a database key lookup.

---

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/process` | Blurs an uploaded image using the chosen method + intensity. Returns the blurred image (base64) and its hash. **Does not store anything.** |
| `POST /api/store` | Stores an (original, blurred) pair, keyed by the blurred image's hash. Called when the user clicks **Save** or **Copy**. Returns `"already_stored"` if that exact pair already exists. |
| `POST /api/find` | Hashes an uploaded image and looks up a matching stored pair. Returns the original on a match, or a 404 with a clear "not found" message otherwise. |

---

## Web Demo — Pages

### 1. Landing Page
Welcome screen with a short explanation of the problem BlurTrace addresses, and two entry points: **Convert to Blur** and **Find the Original**.

### 2. Convert to Blur
- Upload an image (drag & drop, browse, or **paste with Ctrl+V**).
- View the **Original** and **Blurred Preview** side by side.
- Choose **Gaussian Blur** or **Pixelation**, and adjust the **intensity slider** for a live-updating preview.
- **Save** downloads the blurred image and stores the pair in the database.
- **Copy** copies the blurred image to the clipboard and also stores the pair.

### 3. Find the Original
- Upload a blurred image (drag & drop, browse, or paste).
- Click **Find Original** to search for a match by hash.
- On a match: view and download the original image.
- On no match: a clear message explains that nothing was found.

---

## Running the Project

```bash
# 1. Backend setup
cd backend
python -m venv venv
source venv/Scripts/activate      # Git Bash on Windows
pip install -r requirements.txt

# 2. Configure the database
cp .env.example .env              # then fill in your local Postgres credentials

# 3. Run the server (also serves the frontend)
python -m uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000/** in your browser.

---

## Scope & Limitations

These are intentional design decisions for this case study, not oversights:

- **No encryption** — original and blurred images are stored as plain bytes.
- **No authentication** — anyone running the app locally can store or look up any pair. Fine for a local, single-user demo only.
- **Single table design** — one `image_pairs` table rather than normalized tables.
- **Exact-match hashing only** — matching is based on exact pixel content, not perceptual/fuzzy similarity. A blurred image produced by any tool other than BlurTrace, or a lossy re-compression of a BlurTrace-produced image, will not match.
- **Closed-loop system** — BlurTrace can only recognize blurred images it produced itself; it is not a general "trace any blurred image" tool.

---

*Student case study project — local demo, not intended for real sensitive images.*