from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048


def validate_endpoint_url(url: str, *, allow_http: bool = False) -> str:
    """Return the normalised URL or raise ValueError with a user-facing message."""
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("URL is too long")

    parts = urlsplit(url)
    allowed = {"https", "http"} if allow_http else {"https"}
    if parts.scheme not in allowed:
        raise ValueError("URL must use https" if not allow_http else "URL must use http or https")
    if not parts.hostname:
        raise ValueError("URL must include a hostname")
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials")
    return url