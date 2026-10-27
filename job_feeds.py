"""Public board endpoints and feed-shape validation shared by scans and checks."""

BOARD_APIS = {
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


def board_url(ats, board):
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
