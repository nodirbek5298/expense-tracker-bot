import os
import tempfile
import unittest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import db  # noqa: E402


class DbTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(db.DB_PATH):
            os.remove(db.DB_PATH)
        db.init_db()

    def test_add_and_summary(self):
        db.add_expense(1, 25000, "tushlik")
        db.add_expense(1, 15000, "taksi")
        db.add_expense(1, 5000, "tushlik")
        rows = db.summary_by_category(1, db.period_start("today"))
        totals = {r["category"]: r["total"] for r in rows}
        self.assertEqual(totals, {"tushlik": 30000, "taksi": 15000})

    def test_users_are_isolated(self):
        db.add_expense(1, 1000, "a")
        db.add_expense(2, 2000, "b")
        self.assertEqual(len(db.last_expenses(1)), 1)
        self.assertEqual(db.last_expenses(2)[0]["amount"], 2000)

    def test_delete_only_own(self):
        eid = db.add_expense(1, 1000, "a")
        self.assertFalse(db.delete_expense(2, eid))
        self.assertTrue(db.delete_expense(1, eid))
        self.assertEqual(db.last_expenses(1), [])

    def test_periods(self):
        for p in ("today", "week", "month"):
            self.assertRegex(db.period_start(p), r"^\d{4}-\d{2}-\d{2}$")
        with self.assertRaises(ValueError):
            db.period_start("year")

    def test_delete_all(self):
        db.add_expense(1, 1, "a")
        db.add_expense(1, 2, "b")
        db.add_expense(2, 3, "c")
        self.assertEqual(db.delete_all(1), 2)
        self.assertEqual(len(db.last_expenses(2)), 1)


if __name__ == "__main__":
    unittest.main()
