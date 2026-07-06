"""
main.py
-------
FastAPI application exposing three endpoints:

  POST /api/process  -> blur an uploaded image, return blurred bytes + hash (no DB write)
  POST /api/store     -> insert an (original, blurred) pair into the DB, keyed by hash
  POST /api/find      -> look up a stored pair by the exact hash of an uploaded (blurred) image

No authentication, no encryption, single table, exact-hash matching only —
these are intentional scope decisions for this student case study, not bugs.
"""

import base64

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import psycopg2

from algorithms import apply_gaussian_blur, apply_pixelation, sha256_hash_of_pixels
import db

app = FastAPI(title="BlurTrace API")

# Allow the frontend (served separately or via file://) to call these endpoints during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# FastAPI/Starlette's default multipart parser caps EVERY form part (fields and
# files alike) at 1MB unless told otherwise. Real photos and their base64
# encodings are routinely bigger than that, so every endpoint below parses the
# form manually via request.form(max_part_size=...) instead of using the
# automatic File()/Form() parameter injection, which doesn't expose this option.
MAX_PART_SIZE = 25 * 1024 * 1024  # 25MB per field/file, generous for a student demo


@app.on_event("startup")
def on_startup():
    """Ensure the image_pairs table exists as soon as the server starts."""
    db.init_db()


@app.post("/api/process")
async def process_image(request: Request):
    """
    Blur an uploaded image. Does NOT store anything in the database.
    Returns the blurred image as base64 plus its SHA-256 hash, so the
    frontend can live-preview and later call /api/store only when the
    user actually clicks Save or Copy.

    Expects multipart form fields: file, method ("gaussian"|"pixelate"), intensity (1-10)
    """
    form = await request.form(max_part_size=MAX_PART_SIZE)

    if "file" not in form or "method" not in form or "intensity" not in form:
        raise HTTPException(status_code=400, detail="file, method, and intensity are all required")

    method = form["method"]
    try:
        intensity = int(form["intensity"])
    except ValueError:
        raise HTTPException(status_code=400, detail="intensity must be an integer between 1 and 10")

    if method not in ("gaussian", "pixelate"):
        raise HTTPException(status_code=400, detail="method must be 'gaussian' or 'pixelate'")
    if not (1 <= intensity <= 10):
        raise HTTPException(status_code=400, detail="intensity must be between 1 and 10")

    original_bytes = await form["file"].read()
    if not original_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        if method == "gaussian":
            blurred_bytes = apply_gaussian_blur(original_bytes, intensity)
        else:
            blurred_bytes = apply_pixelation(original_bytes, intensity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    blurred_hash = sha256_hash_of_pixels(blurred_bytes)

    return JSONResponse({
        "blurred_image_base64": base64.b64encode(blurred_bytes).decode("utf-8"),
        "blurred_hash": blurred_hash,
        "method": method,
        "intensity": intensity,
    })


@app.post("/api/store")
async def store_image(request: Request):
    """
    Store an (original, blurred) pair in the database, keyed by blurred_hash.
    Called when the user clicks Save or Copy on the Convert to Blur page.

    Expects multipart form fields: original_file, blurred_image_base64, blurred_hash, method

    If this exact blurred_hash is already stored, we don't error out -- we
    report it as already-stored, matching the UI's "Already stored in
    database" confirmation message.
    """
    form = await request.form(max_part_size=MAX_PART_SIZE)

    required = ("original_file", "blurred_image_base64", "blurred_hash", "method")
    missing = [k for k in required if k not in form]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required field(s): {', '.join(missing)}")

    original_bytes = await form["original_file"].read()
    if not original_bytes:
        raise HTTPException(status_code=400, detail="Original file is empty")

    blurred_hash = form["blurred_hash"]
    method = form["method"]

    try:
        blurred_bytes = base64.b64decode(form["blurred_image_base64"])
    except Exception:
        raise HTTPException(status_code=400, detail="blurred_image_base64 is not valid base64")

    # Defensive check: does the hash actually match the blurred bytes we were sent?
    try:
        computed_hash = sha256_hash_of_pixels(blurred_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if computed_hash != blurred_hash:
        raise HTTPException(
            status_code=400,
            detail="blurred_hash does not match the hash of the provided blurred image bytes"
        )

    if db.hash_already_stored(blurred_hash):
        return JSONResponse({"status": "already_stored", "blurred_hash": blurred_hash})

    try:
        image_id = db.store_pair(original_bytes, blurred_bytes, blurred_hash, method)
    except psycopg2.errors.UniqueViolation:
        # Race condition: got stored between our check and our insert.
        return JSONResponse({"status": "already_stored", "blurred_hash": blurred_hash})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error while storing: {e}")

    return JSONResponse({"status": "stored", "image_id": image_id, "blurred_hash": blurred_hash})


@app.post("/api/find")
async def find_original(request: Request):
    """
    Look up the original image matching an uploaded blurred image, by exact
    SHA-256 hash of the uploaded file's bytes.

    Expects multipart form field: file

    Returns 404 if no matching row exists -- this is expected and normal
    for any blurred image not produced by this system's Convert flow.
    """
    form = await request.form(max_part_size=MAX_PART_SIZE)

    if "file" not in form:
        raise HTTPException(status_code=400, detail="file is required")

    uploaded_bytes = await form["file"].read()
    if not uploaded_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        uploaded_hash = sha256_hash_of_pixels(uploaded_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        row = db.find_original_by_hash(uploaded_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error while searching: {e}")

    if row is None:
        raise HTTPException(status_code=404, detail="No matching original found for this image.")

    return JSONResponse({
        "image_id": str(row["image_id"]),
        "original_image_base64": base64.b64encode(bytes(row["original_img"])).decode("utf-8"),
        "blur_method": row["blur_method"],
        "created_at": row["created_at"].isoformat(),
    })


# Serve the frontend as static files (index.html, style.css, app.js) directly from FastAPI.
# This mount must come AFTER the /api/* routes above, so it doesn't shadow them.
# check_dir=False so the backend can still run standalone before the frontend folder exists
# (e.g. while testing endpoints via /docs). Once frontend/ exists, requests to "/" will serve it.
app.mount("/", StaticFiles(directory="../frontend", html=True, check_dir=False), name="frontend")