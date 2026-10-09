"""
Barrier-burden bands derived from the WPI quantiles in the model artifacts.

WPI is a barrier index: LOWER is better. Every screen that colours or
groups patients by WPI goes through this module so the thresholds are
defined exactly once.
"""

import math

from model import PHENOTYPE_REFERENCE_DATASET, QUANTILE_BANDS


# (key, label, colour token) in order from best to worst.
BANDS = [
    ("lower", "Lower barrier burden", "good"),
    ("lower-mid", "Lower-intermediate barrier burden", "mid"),
    ("higher-mid", "Higher-intermediate barrier burden", "warn"),
    ("higher", "Higher barrier burden", "bad"),
]

BAND_KEYS = [key for key, _label, _var in BANDS]

THRESHOLDS = [
    float(QUANTILE_BANDS.get("q25", 0)),
    float(QUANTILE_BANDS.get("q50", 0)),
    float(QUANTILE_BANDS.get("q75", 0)),
]


def _wpi_scale_max():
    """Upper end of WPI gauges, rounded up to the next 5."""

    try:
        top = float(PHENOTYPE_REFERENCE_DATASET["WPI"].max())
    except (KeyError, TypeError, ValueError):
        top = float(QUANTILE_BANDS.get("q95", 60)) * 1.2

    return float(math.ceil(top / 5) * 5)


WPI_SCALE_MAX = _wpi_scale_max()


def band_index(wpi):
    for index, threshold in enumerate(THRESHOLDS):
        if wpi <= threshold:
            return index

    return len(BANDS) - 1


def band_info(wpi):
    """
    Everything a template needs to show a WPI band:
    {"key", "label", "short", "var", "cls"}.
    """

    if wpi is None:
        return {
            "key": "",
            "label": "Not assessed",
            "short": "Not assessed",
            "var": "ink-3",
            "cls": "p-soft",
        }

    key, label, var = BANDS[band_index(float(wpi))]

    return {
        "key": key,
        "label": label,
        "short": label.replace(" barrier burden", ""),
        "var": var,
        "cls": f"p-{var}",
    }


def gauge_bands():
    """Band segments for WPI gauges: [{"to": value, "var": token}, ...]."""

    edges = THRESHOLDS + [WPI_SCALE_MAX]

    return [
        {"to": round(edge, 2), "var": var}
        for edge, (_key, _label, var) in zip(edges, BANDS)
    ]
