"""Public board endpoints and feed-shape validation shared by scans and checks."""

BOARD_APIS = {
    "workday": {
        "url": "https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs",
        "key": "jobPostings",
    },
    "greenhouse": {
        "url": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
        "key": "jobs",
    },
    "lever": {
        "url": "https://api.lever.co/v0/postings/{board}?mode=json",
        "key": None,
    },
    "ashby": {
        "url": "https://api.ashbyhq.com/posting-api/job-board/{board}",
        "key": "jobs",
    },
}


def company_board(company):
    """Return the common board identifier for any configured company."""
    if company["ats"] == "workday":
        return "/".join(company[key] for key in ("tenant", "site", "host"))
    return company["board"]


def board_url(ats, board):
    if ats == "workday":
        tenant, site, host = board.split("/")
        return BOARD_APIS[ats]["url"].format(tenant=tenant, site=site, host=host)
    return BOARD_APIS[ats]["url"].format(board=board)


def feed_items(data, key=None):
    """Return job records, or None for a malformed feed; an empty list is valid."""
    if key is not None:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    if not isinstance(data, list):
        return None
    if not all(isinstance(job, dict) and job.get("id") is not None for job in data):
        return None
    return data
