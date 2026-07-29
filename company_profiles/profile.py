"""Company profile data model.

A profile describes the company under analysis and the competitors it is
benchmarked against. It supplies the facts that cannot be derived from a
company name alone — sector themes and each competitor's reporting segments —
which the extraction prompts turn into targeted searches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ProfileError(ValueError):
    """Raised when a profile file is missing required fields or malformed."""


@dataclass(frozen=True)
class Competitor:
    """A single competitor and its reporting segments.

    Segments are per-competitor because they differ between companies —
    Microsoft reports "Intelligent Cloud" where Amazon reports "AWS".
    """

    name: str
    segments: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict, *, source: str) -> "Competitor":
        if not isinstance(data, dict):
            raise ProfileError(
                f"{source}: each entry in 'competitors' must be an object, "
                f"got {type(data).__name__}"
            )
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ProfileError(f"{source}: every competitor needs a non-empty 'name'")
        segments = data.get("segments", [])
        if not isinstance(segments, list) or not all(
            isinstance(s, str) for s in segments
        ):
            raise ProfileError(
                f"{source}: 'segments' for {name} must be a list of strings"
            )
        return cls(name=name, segments=tuple(segments))


@dataclass(frozen=True)
class CompanyProfile:
    """Everything the agents need to know about who they are analysing."""

    company_name: str
    sector: str
    customer_label: str
    sector_themes: tuple[str, ...]
    competitors: tuple[Competitor, ...]

    @property
    def competitor_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.competitors)

    @property
    def competitor_list(self) -> str:
        """Human-readable competitor list, e.g. 'Microsoft and Amazon'."""
        names = self.competitor_names
        if not names:
            return "the competitor set"
        if len(names) == 1:
            return names[0]
        return f"{', '.join(names[:-1])} and {names[-1]}"

    @classmethod
    def from_dict(cls, data: dict, *, source: str = "<profile>") -> "CompanyProfile":
        required = ("company_name", "sector", "competitors")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ProfileError(f"{source}: missing required field(s): {', '.join(missing)}")

        competitors = data["competitors"]
        if not isinstance(competitors, list):
            raise ProfileError(f"{source}: 'competitors' must be a list")

        themes = data.get("sector_themes", [])
        if not isinstance(themes, list) or not all(isinstance(t, str) for t in themes):
            raise ProfileError(f"{source}: 'sector_themes' must be a list of strings")

        company_name = data["company_name"]
        return cls(
            company_name=company_name,
            sector=data["sector"],
            # Default the deployment label to a slug of the company name so a
            # profile does not have to spell it out.
            customer_label=data.get("customer_label") or company_name.lower().replace(" ", "-"),
            sector_themes=tuple(themes),
            competitors=tuple(
                Competitor.from_dict(c, source=source) for c in competitors
            ),
        )

    @classmethod
    def from_file(cls, path: Path) -> "CompanyProfile":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{path.name}: invalid JSON — {exc}") from exc
        return cls.from_dict(data, source=path.name)
