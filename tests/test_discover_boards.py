import unittest
from unittest.mock import Mock, patch

import discover_boards as discover


class SlugTests(unittest.TestCase):
    def test_variants_prefer_the_website_label_then_name_forms(self):
        self.assertEqual(discover.slug_variants("Scale AI", "https://www.scale.com/about"),
                         ["scale", "scaleai", "scale-ai"])
        self.assertEqual(discover.slug_variants("CircuitHub", "https://circuithub.com"), ["circuithub"])
        self.assertEqual(discover.slug_variants("Acme, Inc.", ""), ["acmeinc", "acme-inc"])
        self.assertEqual(discover.slug_variants("", ""), [])

    def test_same_company_is_a_loose_containment_check(self):
        self.assertTrue(discover.same_company("Scale AI", "Scale AI, Inc."))
        self.assertTrue(discover.same_company("Anthropic", "Anthropic"))
        self.assertTrue(discover.same_company("Apple", "Pineapple Labs"))  # loose by design; a human reviews
        self.assertFalse(discover.same_company("Orbit", "Delta Robotics"))
        self.assertFalse(discover.same_company("", "x"))


class ProbeTests(unittest.TestCase):
    def response(self, status, payload=None):
        return Mock(status_code=status, json=lambda: payload)

    def test_counts_matching_internships_and_ignores_missing_boards(self):
        board = {"jobs": [{"id": 1, "title": "Firmware Intern"}, {"id": 2, "title": "Sales Manager"},
                          {"id": 3, "title": "International Lawyer"}]}
        matcher = lambda title: "intern" in title.lower().split()
        with patch.object(discover.requests, "get", return_value=self.response(200, board)):
            self.assertEqual(discover.probe("greenhouse", "acme", matcher), (3, 1, "Firmware Intern"))
        with patch.object(discover.requests, "get", return_value=self.response(404)):
            self.assertIsNone(discover.probe("greenhouse", "nope", matcher))
        with patch.object(discover.requests, "get", side_effect=discover.requests.Timeout()):
            self.assertIsNone(discover.probe("lever", "acme", matcher))

    def test_lever_titles_use_the_text_field_and_bad_schema_is_rejected(self):
        with patch.object(discover.requests, "get",
                          return_value=self.response(200, [{"id": "a", "text": "SWE Intern"}])):
            self.assertEqual(discover.probe("lever", "acme", lambda t: "Intern" in t), (1, 1, "SWE Intern"))
        with patch.object(discover.requests, "get", return_value=self.response(200, {"unexpected": 1})):
            self.assertIsNone(discover.probe("greenhouse", "acme", lambda t: True))


class DiscoverTests(unittest.TestCase):
    def test_only_live_boards_are_reported_and_greenhouse_names_are_checked(self):
        live = {("greenhouse", "acme"): (5, 2, "SWE Intern"), ("ashby", "acme"): (3, 0, "")}
        with patch.object(discover, "probe", side_effect=lambda ats, slug, m: live.get((ats, slug))), \
             patch.object(discover, "board_name", return_value="Acme Robotics"):
            found = discover.discover({"name": "Acme", "website": "https://acme.com"}, lambda t: True)
        self.assertEqual([(e["ats"], e["board"], e["internships"]) for e in found],
                         [("greenhouse", "acme", 2), ("ashby", "acme", 0)])
        self.assertTrue(found[0]["confirmed"])
        self.assertNotIn("confirmed", found[1])


if __name__ == "__main__":
    unittest.main()
