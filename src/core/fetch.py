import os
import time
import httpx
import urllib3

# Suprimir avisos de SSL nao verificado (comum em portos governamentais)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_url(
    url: str,
    timeout: float | None = None,
    retries: int | None = None,
    backoff_sec: float | None = None,
    headers: dict | None = None,
) -> bytes:
    headers = headers or {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    }
    timeout = timeout if timeout is not None else float(os.getenv("FETCH_TIMEOUT", "60"))
    retries = retries if retries is not None else int(os.getenv("FETCH_RETRIES", "2"))
    retries = max(1, retries)
    backoff_sec = backoff_sec if backoff_sec is not None else float(os.getenv("FETCH_BACKOFF", "2"))

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=timeout, verify=False) as client:
                r = client.get(url, headers=headers, follow_redirects=True)
                r.raise_for_status()
                return r.content
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff_sec * (2 ** (attempt - 1)))
            else:
                raise

    raise last_err
