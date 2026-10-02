"""Council v2 — deterministic scoring, identical bundles, signed seat records.

The model gives the scores; the code does the arithmetic.  See README.md in
this directory for the eight rules this package implements and for how to run
it.  Every model call is behind an injectable adapter: the test-suite and the
default CLI mode (``--dry-run --mock``) never open a network connection.
"""

__version__ = "2.0.0-dev"

# Names of the seven rubric criteria, in the canonical order of
# admission/RUBRIC.md.  Other modules import this tuple; do not reorder.
CRITERIA_ORDER = (
    "body_of_work_depth",
    "specialty_uniqueness",
    "voice_personality_clarity",
    "faithful_distillation",
    "synthetic_transparency",
    "placement_fit",
    "continuity_with_class",
)
