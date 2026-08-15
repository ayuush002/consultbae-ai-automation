import tempfile
import unittest
from pathlib import Path

from app.api import create_app
from automation.ingest_and_merge import FILES, run


class CandidateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.database = Path(cls.folder.name) / "test.db"
        run(FILES, cls.database)
        app = create_app(cls.database)
        app.config["TESTING"] = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"candidate_count": 56, "status": "healthy"})

    def test_duplicate_matches_normalized_email_and_phone(self):
        response = self.client.post("/api/candidates/check", json={
            "email": " TANVI.GUPTA31@EXAMPLE.COM ", "phone": "+91-9000000254"
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["duplicate"])
        self.assertEqual(response.json["matched_by"], ["email", "phone"])
        self.assertEqual(response.json["candidates"][0]["full_name"], "Tanvi Gupta")

    def test_new_candidate_is_not_a_duplicate(self):
        response = self.client.post("/api/candidates/check", json={
            "email": "new.person@example.com", "phone": "9876543210"
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["duplicate"])
        self.assertEqual(response.json["candidates"], [])

    def test_invalid_request_has_clear_error(self):
        response = self.client.post("/api/candidates/check", json={"name": "No Identifiers"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid email or phone", response.json["error"])


if __name__ == "__main__":
    unittest.main()
