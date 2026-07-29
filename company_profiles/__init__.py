"""Company profile loading.

Select a profile with the COMPANY_PROFILE environment variable:

    COMPANY_PROFILE=alphabet

Profiles live in company_profiles/data/<name>.json. To onboard a new company,
copy data/example.json and fill it in — no code changes required.
"""

import os
from functools import lru_cache
from pathlib import Path

from .profile import CompanyProfile, Competitor, ProfileError

DATA_DIR = Path(__file__).parent / "data"

# Falls back to the documented template so that importing the agents never
# fails on an unconfigured environment — the same reason the GCP settings use
# os.environ.get() rather than os.environ[].
DEFAULT_PROFILE = "example"


def available_profiles() -> list:
    """Names of every profile shipped in company_profiles/data."""
    return sorted(path.stem for path in DATA_DIR.glob("*.json"))


@lru_cache(maxsize=None)
def load_profile(name: str = "") -> CompanyProfile:
    """Loads a company profile by name, or from COMPANY_PROFILE if unset.

    Args:
        name: Profile name to load. Defaults to the COMPANY_PROFILE
              environment variable, then to the bundled example profile.

    Returns:
        CompanyProfile: The parsed, validated profile.

    Raises:
        ProfileError: If the named profile does not exist or is malformed.
    """
    profile_name = name or os.environ.get("COMPANY_PROFILE", "") or DEFAULT_PROFILE
    path = DATA_DIR / f"{profile_name}.json"
    if not path.is_file():
        raise ProfileError(
            f"No profile named '{profile_name}'. "
            f"Available: {', '.join(available_profiles()) or 'none'}. "
            f"Set COMPANY_PROFILE or add {path.name} to company_profiles/data/."
        )
    return CompanyProfile.from_file(path)


__all__ = [
    "CompanyProfile",
    "Competitor",
    "ProfileError",
    "load_profile",
    "available_profiles",
    "DEFAULT_PROFILE",
]
