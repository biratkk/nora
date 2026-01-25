"""Fetch tool for retrieving web content."""

from strands import tool


@tool(name="Fetch")
def fetch_url(url: str) -> str:
    """Fetch the HTML content of a website.
    
    Args:
        url: The URL to fetch (must include http:// or https://)
    """
    import urllib.request
    import urllib.error
    
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Nora/1.0)"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return f"Warning: Content-Type is '{content_type}', may not be HTML.\n\n" + response.read().decode("utf-8", errors="replace")
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ValueError(f"URL error: {e.reason}")
    except TimeoutError:
        raise ValueError("Request timed out")
