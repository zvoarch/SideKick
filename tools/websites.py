"""Local website validation and browser launching helpers."""

from urllib.parse import urlsplit, urlunsplit
import webbrowser


def normalize_website_url(value):
    """Normalize a domain or HTTP(S) URL and reject unsafe/non-web schemes."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a website name or URL.")

    value = value.strip()
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("The website URL cannot contain spaces or control characters.")
    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing .port validates malformed port numbers.
        _ = parsed.port
    except ValueError as error:
        raise ValueError("That website URL is not valid.") from error

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS websites can be opened.")
    if not hostname or parsed.username or parsed.password:
        raise ValueError("Enter a valid website URL without login credentials.")
    if "." not in hostname and hostname.lower() != "localhost":
        raise ValueError("Enter a full website URL, such as reddit.com.")

    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def open_website(url):
    """Open an HTTP(S) URL in the user's default browser."""
    normalized_url = normalize_website_url(url)
    try:
        opened = webbrowser.open(normalized_url, new=2)
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        return {"ok": False, "message": "The website could not be opened in the default browser."}
    return {"ok": True, "message": "Opened the website in the default browser."}
