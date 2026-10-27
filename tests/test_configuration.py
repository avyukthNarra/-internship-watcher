import json
import unittest

from project_config import (follow_up_days, load_personal_webhooks,
                            notifications_enabled, validate_config)


class ConfigurationTests(unittest.TestCase):
    def test_bad_feed_options_fail_before_a_scan(self):
        invalid = [
            ({"simplify": []}, "simplify must be an object"),
            ({"simplify": {"company_keywords": "Postman"}}, "simplify.company_keywords"),
            ({"simplify": {"max_age_days": True}}, "simplify.max_age_days"),
            ({"jobright": {"repos": "internships"}}, "jobright.repos"),
            ({"jobright": {"enabled": "false"}}, "jobright.enabled"),
            ({"keep_unknown_terms": "false"}, "keep_unknown_terms"),
        ]
        for options, message in invalid:
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                validate_config({"companies": [], **options})

    def test_invalid_webhook_mapping_does_not_partially_modify_environment(self):
        environ = {"PERSONAL_WEBHOOKS_JSON": json.dumps({
            "DISCORD_WEBHOOK_MEMBER": "https://discord.test/member", "OTHER_TOKEN": "bad",
        })}
        before = dict(environ)
        with self.assertRaises(ValueError):
            load_personal_webhooks(environ)
        self.assertEqual(environ, before)

    def test_webhook_mapping_preserves_explicit_environment_override(self):
        environ = {
            "PERSONAL_WEBHOOKS_JSON": '{"DISCORD_WEBHOOK_MEMBER":"mapped"}',
            "DISCORD_WEBHOOK_MEMBER": "explicit",
        }
        load_personal_webhooks(environ)
        self.assertEqual(environ["DISCORD_WEBHOOK_MEMBER"], "explicit")

    def test_partial_credentials_do_not_enable_delivery(self):
        self.assertFalse(notifications_enabled({}, {"SMTP_USER": "member"}))
        self.assertFalse(notifications_enabled({}, {"NOTION_TOKEN": "token"}))
        self.assertTrue(notifications_enabled({}, {"SMTP_USER": "member", "SMTP_PASS": "password"}))
        cfg = {"profiles": {"u": {"webhook_env": "DISCORD_WEBHOOK_MEMBER"}}}
        self.assertTrue(notifications_enabled(cfg, {"DISCORD_WEBHOOK_MEMBER": "hook"}))

    def test_zero_follow_up_days_overrides_both_defaults(self):
        cfg = {"follow_up_days": 21, "profiles": {"u": {"follow_up_days": 0}}}
        self.assertEqual(follow_up_days(cfg, "u"), 0)
        self.assertEqual(follow_up_days(cfg, "other"), 21)
        self.assertEqual(follow_up_days({}, "other"), 14)
