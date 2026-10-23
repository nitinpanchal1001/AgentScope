import re
import unicodedata

NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, fallback: str, max_length: int = 80) -> str:
    """Create a bounded, URL-safe identifier from a display name."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = NON_ALPHANUMERIC.sub("-", normalized.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or fallback


def append_slug_suffix(slug: str, suffix: str, *, max_length: int = 80) -> str:
    bounded_suffix = NON_ALPHANUMERIC.sub("", suffix.lower())[:12]
    if not bounded_suffix:
        raise ValueError("slug suffix must contain an alphanumeric character")
    prefix = slug[: max_length - len(bounded_suffix) - 1].rstrip("-")
    return f"{prefix}-{bounded_suffix}"
