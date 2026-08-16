import io
import math
import sqlite3
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from app.api import create_app
from automation.ingest_and_merge import FILES, run


def wav_file(duration=0.25, sample_rate=16000, frequency=440):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        samples = [int(0.25 * 32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
                   for i in range(int(duration * sample_rate))]
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    output.seek(0)
    return output


class AudioAppTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.database = root / "test.db"
        self.uploads = root / "uploads"
        run(FILES, self.database)
        app = create_app(self.database, self.uploads)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self.folder.cleanup()

    def test_submission_extracts_metadata_and_links_existing_candidate(self):
        response = self.client.post("/submit", data={
            "name": "Tanvi Gupta",
            "phone": "+91-9000000254",
            "audio": (wav_file(), "sample.wav"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Audio submissions", response.data)
        self.assertIn(b"16.0 kHz", response.data)
        self.assertIn(b"256.0 kbps", response.data)
        with sqlite3.connect(self.database) as db:
            item = db.execute("""SELECT a.candidate_id, a.duration_seconds, a.sample_rate_hz,
                a.bitrate_kbps, a.loudness_dbfs FROM audio_submissions a""").fetchone()
            tanvi_id = db.execute("SELECT id FROM candidates WHERE phone='9000000254'").fetchone()[0]
        self.assertEqual(item[0], tanvi_id)
        self.assertAlmostEqual(item[1], 0.25)
        self.assertEqual(item[2], 16000)
        self.assertEqual(item[3], 256.0)
        self.assertLess(item[4], 0)

    def test_new_phone_creates_candidate(self):
        self.client.post("/submit", data={
            "name": "New Worker", "phone": "9876543210", "audio": (wav_file(), "new.wav")
        }, content_type="multipart/form-data")
        with sqlite3.connect(self.database) as db:
            candidate = db.execute("SELECT full_name,data_sources FROM candidates WHERE phone='9876543210'").fetchone()
        self.assertEqual(candidate, ("New Worker", "audio_app"))

    def test_fake_wav_is_rejected_and_deleted(self):
        response = self.client.post("/submit", data={
            "name": "Test Worker", "phone": "9876543210",
            "audio": (io.BytesIO(b"this is not audio"), "fake.wav"),
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"not a valid PCM WAV", response.data)
        self.assertEqual(list(self.uploads.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
