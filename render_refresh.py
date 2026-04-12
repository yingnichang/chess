from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    hostport = os.getenv("WEB_APP_HOSTPORT", "").strip()
    refresh_token = os.getenv("REFRESH_TOKEN", "").strip()
    if not hostport:
        print("WEB_APP_HOSTPORT is required", file=sys.stderr)
        return 2

    url = f"http://{hostport}/admin/refresh"
    params = {"token": refresh_token} if refresh_token else {}
    response = requests.post(url, params=params, timeout=300)
    print(response.status_code)
    print(response.text)
    response.raise_for_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
