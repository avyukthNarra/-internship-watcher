import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import verify_boards


class BoardVerifierTests(unittest.TestCase):
    def test_bad_schema_is_not_reported_as_an_empty_healthy_board(self):
        response = Mock(status_code=200)
        response.json.return_value = {"other": []}
        with patch.object(verify_boards.requests, "get", return_value=response):
            result = verify_boards.check(("Wayve", "ashby", "wayve"))
        self.assertEqual(result[3:], (-1, "Unexpected feed schema"))

    def test_empty_valid_board_succeeds(self):
        response = Mock(status_code=200)
        response.json.return_value = {"jobs": []}
        with patch.object(verify_boards.requests, "get", return_value=response):
            result = verify_boards.check(("Wayve", "ashby", "wayve"))
        self.assertEqual(result[3:], (0, None))

    def test_http_failure_reports_status(self):
        with patch.object(verify_boards.requests, "get", return_value=Mock(status_code=404)):
            result = verify_boards.check(("Missing", "greenhouse", "missing"))
        self.assertEqual(result[3:], (-1, "HTTP 404"))

    def test_default_checks_configured_boards_and_selection_is_case_insensitive(self):
        companies = [{"name": "Wayve", "ats": "ashby", "board": "wayve"},
                     {"name": "Other", "ats": "lever", "board": "other"}]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"companies": companies}))
            with patch.object(verify_boards, "check", side_effect=lambda c: (*c, 1, None)) as check, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify_boards.main(["--config", str(config)]), 0)
                self.assertEqual(check.call_count, 2)
                check.reset_mock()
                self.assertEqual(verify_boards.main(["--config", str(config), "--company", "WAYVE"]), 0)
                check.assert_called_once_with(("Wayve", "ashby", "wayve"))

    def test_candidate_does_not_read_configuration_and_failure_returns_nonzero(self):
        with patch.object(verify_boards, "load_json") as load, \
             patch.object(verify_boards, "check", return_value=("missing", "ashby", "missing", -1, "HTTP 404")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(verify_boards.main(["--candidate", "ashby", "missing"]), 1)
        load.assert_not_called()
        self.assertIn("HTTP 404", output.getvalue())
