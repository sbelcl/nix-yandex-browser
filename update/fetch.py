#!/usr/bin/env python3

"""Shared HTTP helper for the updater scripts.

The scheduled workflow has failed on a transient network error before: the
Yandex host closed a connection mid-request, urllib3 raised
RemoteDisconnected, and because the call site was a bare `requests.get` the
exception propagated all the way out and took the whole job down with exit
code 1. Retrying is the right response to that class of failure — the next
scheduled run succeeded with no changes on our side.

Not named http.py on purpose: the updaters are run as `python3 update/*.py`,
which puts this directory first on sys.path, so a module named `http` here
would shadow the stdlib package that requests itself imports.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Generous, since this runs unattended on a schedule twice a day — the cost of
# waiting out a blip is far lower than the cost of a red build and a missed
# hash update.
TIMEOUT = 30

_RETRY = Retry(
    total=5,
    # 0s, 2s, 4s, 8s, 16s — 30s of backoff across the retries.
    backoff_factor=2,
    status_forcelist=(429, 500, 502, 503, 504),
    # Only GET, so retrying is always safe.
    allowed_methods=frozenset(['GET']),
    # Hand the response back on a final 5xx rather than raising, so callers
    # keep their existing `response.ok` handling.
    raise_on_status=False,
)


def get(url, timeout=TIMEOUT):
    """GET `url`, retrying connection errors, read errors and 5xx responses.

    Returns the final response. A request that still fails after every retry
    raises, exactly as `requests.get` did before.
    """
    with requests.Session() as session:
        adapter = HTTPAdapter(max_retries=_RETRY)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session.get(url, timeout=timeout)
