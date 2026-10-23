from agentscope_api.core.slugs import append_slug_suffix, slugify


def test_slugify_normalizes_names_and_has_a_fallback() -> None:
    assert slugify("  Café Support / EU  ", fallback="project") == "cafe-support-eu"
    assert slugify("🚀", fallback="project") == "project"


def test_slug_suffix_stays_within_storage_limit() -> None:
    result = append_slug_suffix("a" * 80, "A1B2C3D4")
    assert result.endswith("-a1b2c3d4")
    assert len(result) == 80
