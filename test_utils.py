import unittest

from utils import fmt_money, parse_expense


class ParseExpenseTests(unittest.TestCase):
    def test_amount_first(self):
        self.assertEqual(parse_expense("25000 tushlik"), (25000, "tushlik"))

    def test_amount_last(self):
        self.assertEqual(parse_expense("taksi 15000"), (15000, "taksi"))

    def test_spaces_in_amount(self):
        self.assertEqual(parse_expense("25 000 tushlik"), (25000, "tushlik"))

    def test_k_suffix(self):
        self.assertEqual(parse_expense("taksi 15k"), (15000, "taksi"))

    def test_ming_suffix(self):
        self.assertEqual(parse_expense("120 ming kiyim"), (120000, "kiyim"))

    def test_word_starting_with_k_is_not_suffix(self):
        self.assertEqual(parse_expense("15000 kitob"), (15000, "kitob"))

    def test_no_category(self):
        self.assertEqual(parse_expense("50000"), (50000, "boshqa"))

    def test_multiword_category(self):
        self.assertEqual(parse_expense("18000 non va sut"), (18000, "non va sut"))

    def test_no_number(self):
        self.assertIsNone(parse_expense("salom"))

    def test_zero(self):
        self.assertIsNone(parse_expense("0 hech narsa"))

    def test_empty(self):
        self.assertIsNone(parse_expense(""))


class FormatTests(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt_money(1250000), "1 250 000 so'm")
        self.assertEqual(fmt_money(500), "500 so'm")


if __name__ == "__main__":
    unittest.main()
