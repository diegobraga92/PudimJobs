"""Source config contracts: form metadata plus fail-fast validation."""

from app.models.enums import SourceType


def provider_metadata() -> list[dict]:
    """Discovery providers with their config contract (drives the form)."""
    from scrapers.discovery import DISCOVERY_PROVIDERS

    return [
        {
            "name": cls.provider_name,
            "family": cls.family,
            "requires_key": cls.requires_key,
            **_contract(cls.config_metadata()),
        }
        for cls in DISCOVERY_PROVIDERS.values()
    ]


def adapter_metadata() -> list[dict]:
    """Aggregator adapters with their config contract (drives the form)."""
    from scrapers.aggregator import AGGREGATOR_ADAPTERS

    return [
        {
            "name": cls.adapter_name,
            "description": _first_line(cls.__doc__),
            **_contract(cls.config_metadata()),
        }
        for cls in AGGREGATOR_ADAPTERS.values()
    ]


def validate_source_config(source_type: SourceType, config: dict | None) -> None:
    """Raise ``ValueError`` when the config cannot drive its scraper."""
    config = config or {}
    if source_type == SourceType.discovery:
        from scrapers.discovery import DISCOVERY_PROVIDERS

        name = config.get("provider")
        if not name:
            raise ValueError(
                "discovery sources require config['provider'] (see GET /api/sources/providers)"
            )
        scraper_cls = DISCOVERY_PROVIDERS.get(str(name))
        if scraper_cls is None:
            raise ValueError(
                f"unknown discovery provider {name!r} (known: {_known(DISCOVERY_PROVIDERS)})"
            )
        _check_contract(scraper_cls.config_metadata(), config, f"provider {name!r}")
    elif source_type == SourceType.aggregator:
        from scrapers.aggregator import AGGREGATOR_ADAPTERS, GenericHtmlListScraper

        name = config.get("adapter") or GenericHtmlListScraper.adapter_name
        scraper_cls = AGGREGATOR_ADAPTERS.get(str(name))
        if scraper_cls is None:
            raise ValueError(
                f"unknown aggregator adapter {name!r} (known: {_known(AGGREGATOR_ADAPTERS)})"
            )
        _check_contract(scraper_cls.config_metadata(), config, f"adapter {name!r}")


def _contract(metadata: dict) -> dict:
    """Normalize a scraper's metadata into the API payload shape."""
    return {
        "required_config": list(metadata.get("required") or ()),
        "required_any": [list(group) for group in metadata.get("required_any") or ()],
        "optional_config": list(metadata.get("optional") or ()),
        "example_config": dict(metadata.get("example") or {}),
    }


def _check_contract(metadata: dict, config: dict, label: str) -> None:
    """Collect the missing keys of one contract and raise once, if any."""
    missing = [key for key in metadata.get("required") or () if not config.get(key)]
    for group in metadata.get("required_any") or ():
        if not any(config.get(key) for key in group):
            missing.append(" or ".join(group))
    if missing:
        raise ValueError(f"{label} requires config: {', '.join(missing)}")


def _known(registry: dict) -> str:
    return ", ".join(sorted(registry))


def _first_line(text: str | None) -> str | None:
    if not text:
        return None
    return text.strip().splitlines()[0]
