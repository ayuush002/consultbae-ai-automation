import sqlite3
import tempfile
import unittest
from pathlib import Path
import pandas as pd

from automation.ingest_and_merge import FILES, SchemaError, city, ctc, date, email, phone, rate, run


class CleaningTests(unittest.TestCase):
    def test_email_is_trimmed_and_lowercase(self):
        self.assertEqual(email(" TEST@Example.COM "), "test@example.com")

    def test_indian_phone_formats_match(self):
        expected = "9000000143"
        self.assertEqual(phone("+91-9000000143"), expected)
        self.assertEqual(phone("09000000143"), expected)

    def test_city_aliases(self):
        self.assertEqual(city(" GURGAON "), "Gurugram")
        self.assertEqual(city("Bangalore"), "Bengaluru")
        self.assertEqual(city("New Delhi"), "Delhi NCR")

    def test_mixed_ctc_units(self):
        self.assertEqual(ctc(4.2), 420000)
        self.assertEqual(ctc(417964), 417964)

    def test_mixed_dates(self):
        self.assertEqual(date("24-07-2026"), "2026-07-24")
        self.assertEqual(date("07/13/2026"), "2026-07-13")
        self.assertEqual(date("7 Jul 2026"), "2026-07-07")

    def test_rate_keeps_its_period(self):
        self.assertEqual(rate("1415/hr"), (1415, "hour"))
        self.assertEqual(rate("72k/month"), (72000, "month"))


class PipelineTests(unittest.TestCase):
    def test_assignment_files_produce_audited_database(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "test.db"
            summary = run(FILES, database)
            self.assertEqual(summary["raw rows"], 105)
            self.assertEqual(summary["accepted rows"], 103)
            self.assertEqual(summary["repaired rows"], 1)
            self.assertEqual(summary["rejected rows"], 2)
            self.assertEqual(summary["unique candidates"], 56)
            with sqlite3.connect(database) as db:
                arjuns = db.execute(
                    "SELECT phone, source_row_count FROM candidates WHERE full_name='Arjun Mehta' ORDER BY phone"
                ).fetchall()
                self.assertEqual(arjuns, [(None, 1), ("9000000131", 2), ("9000000272", 1)])

    def test_extra_columns_and_known_column_aliases_are_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            changed=Path(folder)/"renamed.csv"
            frame=pd.read_csv(FILES["naukri"])
            frame["LinkedIn URL"]="https://example.com/profile"
            frame.rename(columns={"Full Name":"Candidate Name","Phone":"Mobile"}).to_csv(changed,index=False)
            selected={**FILES,"naukri":changed}
            summary=run(selected,Path(folder)/"test.db")
            self.assertEqual(summary["raw rows"],105)

    def test_missing_required_column_fails_before_database_is_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            changed=Path(folder)/"missing.csv"; database=Path(folder)/"existing.db"
            pd.read_csv(FILES["naukri"]).drop(columns=["Email"]).to_csv(changed,index=False)
            database.write_text("keep this existing database safe")
            with self.assertRaisesRegex(SchemaError,"missing required columns: Email"):
                run({**FILES,"naukri":changed},database)
            self.assertEqual(database.read_text(),"keep this existing database safe")


if __name__ == "__main__":
    unittest.main()
