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

# The lowest reasoning setting each model accepts. GPT-6 Luna rejects "minimal" (its
# lowest value is "none"); Gemini 3.6 Flash accepts thinking level "minimal".
REASONING = {
    "openai": "none",
    "gemini": "minimal",
}

# US dollars per million tokens (input, output), standard paid tier, used for spend limits.
# Reasoning and thinking tokens bill as output. Gemini 3.6 Flash is $0.75 / $3.75 through
# 2026-12-31 and $1.50 / $7.50 from 2027-01-01 (Google AI Studio pricing page, 2026-11-09).
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
