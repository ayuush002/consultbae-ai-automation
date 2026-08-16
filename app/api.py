"""HTTP API used by n8n to check whether a candidate already exists."""
from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from app.audio import AudioValidationError, inspect_wav
from automation.ingest_and_merge import FILES, ROOT, email, phone, run


def create_app(database_path: Path | None = None, upload_folder: Path | None = None) -> Flask:
    app = Flask(__name__)
    database = Path(database_path or os.environ.get("DATABASE_PATH", ROOT / "consultbae.db"))
    uploads = Path(upload_folder or os.environ.get("UPLOAD_FOLDER", ROOT / "uploads"))

    # A deployed service starts without the generated DB because consultbae.db is
    # intentionally not committed. Rebuild it from the fictional CSVs on startup.
    if not database.exists():
        database.parent.mkdir(parents=True, exist_ok=True)
        run(FILES, database)

    app.config["DATABASE_PATH"] = database
    app.config["UPLOAD_FOLDER"] = uploads
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    app.secret_key = os.environ.get("SECRET_KEY", "local-development-key")
    uploads.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS audio_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id),
            submitted_name TEXT NOT NULL,
            submitted_phone TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            duration_seconds REAL NOT NULL,
            sample_rate_hz INTEGER NOT NULL,
            bitrate_kbps REAL NOT NULL,
            loudness_dbfs REAL NOT NULL,
            channels INTEGER NOT NULL,
            quality_estimate TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.post("/submit")
    def submit_audio():
        submitted_name = " ".join(request.form.get("name", "").strip().split())
        submitted_phone = phone(request.form.get("phone"))
        uploaded = request.files.get("audio")
        if not submitted_name or not submitted_phone:
            flash("Enter a valid name and 10-digit Indian phone number.", "error")
            return redirect(url_for("home"))
        if not uploaded or not uploaded.filename or Path(uploaded.filename).suffix.lower() != ".wav":
            flash("Choose an uncompressed WAV audio file.", "error")
            return redirect(url_for("home"))

        original = secure_filename(uploaded.filename)
        stored = f"{uuid.uuid4().hex}.wav"
        destination = uploads / stored
        uploaded.save(destination)
        try:
            metadata = inspect_wav(destination)
            with sqlite3.connect(database) as connection:
                existing = connection.execute("SELECT id FROM candidates WHERE phone=?", (submitted_phone,)).fetchone()
                if existing:
                    candidate_id = existing[0]
                else:
                    cursor = connection.execute(
                        """INSERT INTO candidates
                        (full_name, phone, data_sources, source_row_count)
                        VALUES (?, ?, 'audio_app', 1)""",
                        (submitted_name.title(), submitted_phone),
                    )
                    candidate_id = cursor.lastrowid
                connection.execute(
                    """INSERT INTO audio_submissions
                    (candidate_id, submitted_name, submitted_phone, original_filename, stored_filename,
                     duration_seconds, sample_rate_hz, bitrate_kbps, loudness_dbfs, channels, quality_estimate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (candidate_id, submitted_name, submitted_phone, original, stored,
                     metadata["duration_seconds"], metadata["sample_rate_hz"], metadata["bitrate_kbps"],
                     metadata["loudness_dbfs"], metadata["channels"], metadata["quality_estimate"]),
                )
        except AudioValidationError as error:
            destination.unlink(missing_ok=True)
            flash(str(error), "error")
            return redirect(url_for("home"))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        flash("Audio submitted and analysed successfully.", "success")
        return redirect(url_for("submissions"))

    @app.get("/submissions")
    def submissions():
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            items = connection.execute("SELECT * FROM audio_submissions ORDER BY id DESC").fetchall()
        return render_template("submissions.html", submissions=items)

    @app.get("/uploads/<path:filename>")
    def uploaded_audio(filename: str):
        return send_from_directory(uploads, filename)

    @app.get("/health")
    def health():
        with sqlite3.connect(database) as connection:
            candidate_count = connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        return jsonify(status="healthy", candidate_count=candidate_count)

    @app.post("/api/candidates/check")
    def check_candidate():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Request body must be a JSON object."), 400

        normalized_email = email(payload.get("email"))
        normalized_phone = phone(payload.get("phone"))
        if not normalized_email and not normalized_phone:
            return jsonify(error="Provide at least one valid email or phone number."), 400

        conditions, parameters = [], []
        if normalized_email:
            conditions.append("email = ?")
            parameters.append(normalized_email)
        if normalized_phone:
            conditions.append("phone = ?")
            parameters.append(normalized_phone)

        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            matches = connection.execute(
                f"""SELECT id, full_name, email, phone, city, data_sources
                    FROM candidates WHERE {' OR '.join(conditions)} ORDER BY id""",
                parameters,
            ).fetchall()

        candidates = []
        all_reasons = set()
        for match in matches:
            matched_by = []
            if normalized_email and match["email"] == normalized_email:
                matched_by.append("email")
            if normalized_phone and match["phone"] == normalized_phone:
                matched_by.append("phone")
            all_reasons.update(matched_by)
            candidates.append(
                {
                    "id": match["id"],
                    "full_name": match["full_name"],
                    "email": match["email"],
                    "phone": match["phone"],
                    "city": match["city"],
                    "data_sources": match["data_sources"].split(", "),
                    "matched_by": matched_by,
                }
            )

        return jsonify(
            duplicate=bool(candidates),
            matched_by=sorted(all_reasons),
            normalized_input={"email": normalized_email, "phone": normalized_phone},
            candidates=candidates,
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
