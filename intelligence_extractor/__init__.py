import os

from company_profiles import load_profile

MODEL = os.environ.get("PHOENIX_MODEL", "gemini-2.5-pro")
FLASH_MODEL = os.environ.get("PHOENIX_FLASH_MODEL", "gemini-2.5-flash")

# The company under analysis and its competitors. Selected by COMPANY_PROFILE.
PROFILE = load_profile()
