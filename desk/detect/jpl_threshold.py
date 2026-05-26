"""desk.detect.jpl_threshold — NASA JPL nonparametric dynamic thresholding.

Reference: Hundman et al. (2018), *Detecting Spacecraft Anomalies Using LSTMs
and Nonparametric Dynamic Thresholding* (KDD 2018, arXiv:1802.04431). Original
implementation: github.com/khundman/telemanom.

This module implements the threshold-selection routine on raw windowed
residuals (we skip the LSTM forecaster for the hackathon — for synthetic COTS
telemetry the raw smoothed-difference residuals are sufficient). Returns a
boolean anomaly flag plus magnitude and a regime label that the arbiter
inspects to route between safe-mode-trigger and beam-redirect-draft verbs.

The algorithm searches for the threshold `eps = mu + z * sigma` over a discrete
set of `z` values, picking the `z` that maximises the JPL objective:

    f(z) = (delta_mu / mu  +  delta_sigma / sigma) / (|E_a| + |E_seq|^2)

where E_a is the set of values above the threshold and E_seq is the count of
contiguous anomaly sequences. The objective rewards thresholds that produce
*compact* anomaly sets — discarding both noisy false positives (large |E_a|)
and oversegmented detections (large |E_seq|^2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


# Discrete z search range — JPL uses 2.5..10 in 0.5 steps.
_Z_CANDIDATES = np.arange(2.5, 10.01, 0.5)

# Minimum samples required to call detect(); below this we return is_anomaly=False.
_MIN_WINDOW = 32

# Minimum *peak magnitude* (in sigma units above threshold) required to declare
# an anomaly. On pure Gaussian noise the dynamic_threshold sometimes finds
# spurious z values; requiring the peak to clear the threshold by at least
# this many additional sigmas suppresses those false positives. Set to 1.0
# because the COTS simulator's voltage-droop events partially smear the
# in-window sigma, lowering peak-magnitude for sustained droops; spike-style
# current events still clear by 4+ sigmas.
_MIN_PEAK_MAGNITUDE = 1.0


@dataclass(frozen=True)
class DetectorResult:
    is_anomaly: bool
    magnitude: float
    regime: str
    threshold: float
    mean: float
    std: float
    z: float
    n_above: int
    n_sequences: int


def dynamic_threshold(values: np.ndarray) -> tuple[float, float]:
    """JPL nonparametric threshold selection on `values`.

    Returns `(threshold, z)` where `threshold = mean + z * std` is the value
    above which a point counts as anomalous, picked by the JPL objective.

    If `values` has no positive variance, returns `(+inf, 0.0)` (no threshold
    will trigger).
    """
    v = np.asarray(values, dtype=np.float64)
    n = v.size
    if n < _MIN_WINDOW:
        return float("inf"), 0.0

    mu = float(v.mean())
    sigma = float(v.std(ddof=0))
    if sigma <= 1e-12:
        return float("inf"), 0.0

    best_z = 0.0
    best_score = -np.inf
    best_thresh = float("inf")

    for z in _Z_CANDIDATES:
        eps = mu + z * sigma
        mask = v > eps
        n_above = int(mask.sum())
        if n_above == 0:
            continue

        # Count contiguous anomaly sequences (E_seq).
        # Sequence boundary = transition False -> True in the mask.
        boundaries = np.diff(mask.astype(np.int8))
        n_sequences = int((boundaries == 1).sum())
        # If the run starts with a True point, +1 sequence (no leading False).
        if mask[0]:
            n_sequences += 1

        # Pruned mu and sigma — recompute on the points BELOW the threshold.
        below = v[~mask]
        if below.size < 2:
            continue
        mu_pruned = float(below.mean())
        sigma_pruned = float(below.std(ddof=0))

        delta_mu = mu - mu_pruned
        delta_sigma = sigma - sigma_pruned

        denom = max(1, n_above) + (n_sequences ** 2)
        score = ((delta_mu / mu) + (delta_sigma / sigma)) / denom if mu != 0 else 0.0

        if score > best_score:
            best_score = score
            best_z = z
            best_thresh = float(eps)

    return best_thresh, float(best_z)


def detect(
    window: Sequence[float] | np.ndarray,
    *,
    metric: str = "current_mA",
) -> DetectorResult:
    """Apply the JPL threshold to a 1-D window of telemetry samples.

    `metric` is one of:
      - `"current_mA"`           — anomaly regime label = "see" (latch-up spike)
      - `"voltage_V"`            — anomaly regime label = "dielectric_charge" (rail droop)
      - `"seu_bit_error_rate"`   — anomaly regime label = "see"
      - else                     — regime label = "anomaly"

    For metrics where lower values mean "anomalous" (voltage_V droop), we apply
    the threshold to `-values` and flip the sign of the magnitude.
    """
    v = np.asarray(window, dtype=np.float64)
    n = v.size
    if n < _MIN_WINDOW:
        return DetectorResult(False, 0.0, "insufficient_window", float("inf"),
                              float(v.mean()) if n else 0.0,
                              float(v.std()) if n else 0.0,
                              0.0, 0, 0)

    direction_down = metric == "voltage_V"
    series = -v if direction_down else v

    threshold, z = dynamic_threshold(series)
    mu = float(series.mean())
    sigma = float(series.std())

    if not np.isfinite(threshold):
        return DetectorResult(False, 0.0, "no_variance", float("inf"),
                              mu, sigma, 0.0, 0, 0)

    mask = series > threshold
    n_above = int(mask.sum())
    if n_above == 0:
        return DetectorResult(False, 0.0, "nominal", threshold,
                              mu, sigma, z, 0, 0)

    # Magnitude = (peak - threshold) / sigma  — scale-free anomaly strength.
    peak = float(series.max())
    magnitude = (peak - threshold) / max(sigma, 1e-9)
    if direction_down:
        magnitude = magnitude  # already correct in negated space; reported positive

    # Suppress spurious low-magnitude triggers — true spikes clear by 5+ sigma.
    if magnitude < _MIN_PEAK_MAGNITUDE:
        return DetectorResult(False, magnitude, "nominal", threshold,
                              mu, sigma, z, n_above, 0)

    # Sequence count for regime classification.
    boundaries = np.diff(mask.astype(np.int8))
    n_seq = int((boundaries == 1).sum()) + (1 if mask[0] else 0)

    if metric == "voltage_V":
        regime = "dielectric_charge"
    elif metric == "current_mA":
        regime = "see"
    elif metric == "seu_bit_error_rate":
        regime = "see"
    else:
        regime = "anomaly"

    return DetectorResult(
        is_anomaly=True,
        magnitude=magnitude,
        regime=regime,
        threshold=float(threshold),
        mean=mu,
        std=sigma,
        z=z,
        n_above=n_above,
        n_sequences=n_seq,
    )
