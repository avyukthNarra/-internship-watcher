"""Configuration validation and optional notification credentials."""

import json
import os

from job_feeds import BOARD_APIS

DEFAULT_DISCORD_LIMIT = 50
DEFAULT_DEDUP_DAYS = 30
DEFAULT_FOLLOW_UP_DAYS = 14


def _string_lists(options, keys, prefix=""):
    for key in keys:
        if key in options and (not isinstance(options[key], list)
                               or not all(isinstance(value, str) for value in options[key])):
            raise ValueError(prefix + key + " must be a list of strings")


def _non_negative_integers(options, keys, prefix=""):
    for key in keys:
        if key in options and (type(options[key]) is not int or options[key] < 0):
            raise ValueError(prefix + key + " must be a non-negative integer")


def _booleans(options, keys, prefix=""):
    for key in keys:
        if key in options and not isinstance(options[key], bool):
            raise ValueError(prefix + key + " must be a boolean")


def validate_config(cfg):
    if not isinstance(cfg, dict) or not isinstance(cfg.get("companies"), list):
        raise ValueError("config.json must contain a companies list")
    for company in cfg["companies"]:
        if not isinstance(company, dict) or not all(
                isinstance(company.get(key), str) and company[key]
                for key in ("name", "ats", "board")):
            raise ValueError("Every company needs name, ats, and board strings")
        if company["ats"] not in BOARD_APIS:
            raise ValueError("Unsupported ATS: " + company["ats"])
    _non_negative_integers(cfg, ("max_discord_per_run", "dedup_days", "follow_up_days"))
    _string_lists(cfg, ("terms", "include_keywords", "exclude_keywords", "exclude_locations"))
    _booleans(cfg, ("keep_unknown_terms",))

    for name, list_keys in (("simplify", ("terms", "company_keywords")),
                            ("jobright", ("repos",))):
        feed = cfg.get(name, {})
        if not isinstance(feed, dict):
            raise ValueError(name + " must be an object")
        _string_lists(feed, list_keys, name + ".")
        _non_negative_integers(feed, ("max_age_days",), name + ".")
        _booleans(feed, ("enabled",), name + ".")
        if "url" in feed and not isinstance(feed["url"], str):
            raise ValueError(name + ".url must be a string")

    profiles = cfg.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("profiles must map Discord user IDs to preferences")
    for profile in profiles.values():
        if not isinstance(profile, dict):
            raise ValueError("Each profile must be an object")
        _string_lists(profile, ("roles", "companies", "locations", "terms"), "Profile ")
        _non_negative_integers(profile, ("follow_up_days",), "Profile ")
        _booleans(profile, ("keep_unknown_terms",), "Profile ")
        if "webhook_env" in profile and (not isinstance(profile["webhook_env"], str)
                                         or not profile["webhook_env"].startswith("DISCORD_WEBHOOK_")):
            raise ValueError("Profile webhook_env must begin DISCORD_WEBHOOK_")


def load_personal_webhooks(environ=None):
    """Validate the whole secret before importing any optional webhook variables."""
    environ = os.environ if environ is None else environ
    hooks = json.loads(environ.get("PERSONAL_WEBHOOKS_JSON") or "{}")
    if not isinstance(hooks, dict):
        raise ValueError("PERSONAL_WEBHOOKS_JSON must be an object")
    if not all(name.startswith("DISCORD_WEBHOOK_") and isinstance(value, str)
               for name, value in hooks.items()):
        raise ValueError("Personal webhook keys must begin DISCORD_WEBHOOK_")
    for name, value in hooks.items():
        environ.setdefault(name, value)


def notifications_enabled(cfg, environ=None):
    environ = os.environ if environ is None else environ
    return bool(
        any(environ.get(key) for key in ("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL_TOP"))
        or (environ.get("SMTP_USER") and environ.get("SMTP_PASS"))
        or (environ.get("NOTION_TOKEN") and environ.get("NOTION_PARENT_PAGE_ID"))
        or any(environ.get(profile.get("webhook_env", ""))
               for profile in cfg.get("profiles", {}).values())
    )


def follow_up_days(cfg, user_id):
    return cfg.get("profiles", {}).get(user_id, {}).get(
        "follow_up_days", cfg.get("follow_up_days", DEFAULT_FOLLOW_UP_DAYS))
