"""HTTP API used by n8n to check whether a candidate already exists."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request

from automation.ingest_and_merge import FILES, ROOT, email, phone, run


def create_app(database_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    database = Path(database_path or os.environ.get("DATABASE_PATH", ROOT / "consultbae.db"))

    # A deployed service starts without the generated DB because consultbae.db is
    # intentionally not committed. Rebuild it from the fictional CSVs on startup.
    if not database.exists():
        database.parent.mkdir(parents=True, exist_ok=True)
        run(FILES, database)

    app.config["DATABASE_PATH"] = database

    @app.get("/")
    def home():
        return jsonify(
            service="ConsultBae Candidate API",
            status="running",
            duplicate_check="POST /api/candidates/check",
        )

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
