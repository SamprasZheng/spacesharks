"""desk.detect — anomaly detectors for NEO Action Item 2.

`jpl_threshold.detect(window)` returns a structured `(is_anomaly, magnitude,
regime)` tuple using a NumPy implementation of NASA JPL's Hundman et al. (2018)
*Detecting Spacecraft Anomalies Using LSTMs and Nonparametric Dynamic
Thresholding* — the core threshold-selection routine, not the LSTM forecaster.
"""

from desk.detect.jpl_threshold import detect, dynamic_threshold

__all__ = ["detect", "dynamic_threshold"]
