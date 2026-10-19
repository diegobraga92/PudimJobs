"""Source config contracts: form metadata plus fail-fast validation."""

import re

from app.models.enums import SourceType

#: Config contract of ``manual`` (watchlist) sources. ``cadence_days`` and
#: ``notes`` are optional; ``next_check_at``/``reminded_at`` are engine-managed
#: (see :mod:`app.services.source_watchlist`) and must survive a client update,
#: which is why both UIs merge instead of replacing ``config``.
MANUAL_CONFIG: dict = {
    "required": (),
    "optional": ("cadence_days", "notes"),
    "example": {
        "cadence_days": 7,
        "notes": "anti-bot board — try the serpapi provider later",
    },
}


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


def manual_metadata() -> dict:
    """``manual`` (watchlist) contract: cadence bounds, keys and example.

    Published so neither UI has to hard-code the re-check cadence bounds; the
    validator below enforces exactly these values.
    """
    from app.services.source_watchlist import (
        DEFAULT_CADENCE_DAYS,
        MAX_CADENCE_DAYS,
        MIN_CADENCE_DAYS,
    )

    return {
        "cadence_days": {
            "default": DEFAULT_CADENCE_DAYS,
            "min": MIN_CADENCE_DAYS,
            "max": MAX_CADENCE_DAYS,
        },
        "type": SourceType.manual.value,
        **_contract(MANUAL_CONFIG),
    }


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
        # The key lives in the source's credentials and is often added right
        # after creation, so only the *structure* is proven here (`has_api_key`
        # is unknown): a bad method/body/auth or an unrenderable URL still fails.
        scraper_cls.validate_config(config, has_api_key=None)
    elif source_type == SourceType.aggregator:
        from scrapers.aggregator import AGGREGATOR_ADAPTERS, GenericHtmlListScraper

        name = config.get("adapter") or GenericHtmlListScraper.adapter_name
        scraper_cls = AGGREGATOR_ADAPTERS.get(str(name))
        if scraper_cls is None:
            raise ValueError(
                f"unknown aggregator adapter {name!r} (known: {_known(AGGREGATOR_ADAPTERS)})"
            )
        _check_contract(scraper_cls.config_metadata(), config, f"adapter {name!r}")
        pattern = config.get("exclude_pattern")
        if pattern:
            try:
                re.compile(str(pattern), re.IGNORECASE)
            except re.error as exc:
                raise ValueError(
                    f"aggregator config['exclude_pattern'] is not a valid regex: {exc}"
                ) from exc
    elif source_type == SourceType.manual:
        # Watchlist sources are checked by hand; the only config that drives
        # behaviour is the re-check cadence, which must be a positive integer
        # inside the range published by GET /api/sources/manual-metadata.
        from app.services.source_watchlist import MAX_CADENCE_DAYS, MIN_CADENCE_DAYS

        raw_cadence = config.get("cadence_days")
        if raw_cadence is not None:
            try:
                cadence = int(raw_cadence)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "manual sources require config['cadence_days'] to be an integer"
                ) from exc
            if cadence < MIN_CADENCE_DAYS:
                raise ValueError(
                    f"manual sources require config['cadence_days'] to be "
                    f">= {MIN_CADENCE_DAYS}"
                )
            if cadence > MAX_CADENCE_DAYS:
                raise ValueError(
                    f"manual sources require config['cadence_days'] to be "
                    f"<= {MAX_CADENCE_DAYS}"
                )


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
