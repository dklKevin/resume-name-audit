import math

import pytest

from name_audit.decision import MIXED, PERCEPTION, REAL, ending, overall


@pytest.mark.parametrize(
    ("ir", "rel", "expected"),
    [
        (0.95, 0.05, PERCEPTION),
        (0.90, 0.0999, PERCEPTION),
        (0.90, 0.10, MIXED),
        (0.8999, 0.05, MIXED),
        (0.80, 0.20, MIXED),
        (0.80, 0.33, MIXED),
        (0.7999, 0.0, REAL),
        (1.0, 0.3301, REAL),
        (1.0, math.inf, REAL),
        (0.5, 2.0, REAL),
    ],
)
def test_cutoffs(ir, rel, expected):
    assert ending(ir, rel) == expected


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        ending(float("nan"), 0.1)


def test_worse_model_decides():
    assert overall([PERCEPTION, MIXED]) == MIXED
    assert overall([REAL, PERCEPTION]) == REAL
    assert overall([PERCEPTION, PERCEPTION]) == PERCEPTION
