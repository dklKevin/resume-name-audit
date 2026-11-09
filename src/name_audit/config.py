"""Fixed study settings. Changing anything here after the lock changes the study."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATERIALS = ROOT / "materials"

COMPANY = "Halvorsen Home Supply"
EMAIL_DOMAIN = "gmail.com"

# Model ids as listed by each provider's model list endpoint.
MODELS = {
    "openai": "gpt-6-luna",
    "gemini": "gemini-3.6-flash",
}

# US dollars per million tokens (input, output). Reasoning tokens bill as output.
PRICES = {
    "openai": (0.10, 0.50),
    "gemini": (0.75, 3.75),
}

REPEATS = 2
PILOT_NAME = "David Ryan"
DEGREE_FLOOR = 10.0
PILOT_ADVANCE_RANGE = (0.30, 0.70)
BOOTSTRAP_SAMPLES = 10_000
SEED = 20261107

PROBE_PER_NAME = 2
