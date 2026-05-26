"""tests/test_cots_telemetry.py — NEO Action Item 2 COTS telemetry stream.

Tests that:
  - TelemetryStream emits well-formed samples at the expected fields
  - Buffer accumulates up to WINDOW_SAMPLES
  - Storm weather increases current variance + occasional SEE events
  - regime_hint surfaces `tid` / `see` / `dielectric_charge` over time
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from desk.physics.cots_telemetry import (  # noqa: E402
    TelemetryStream,
    WINDOW_SAMPLES,
    telemetry_buffer_for,
)


def _nominal_weather() -> dict:
    return {"kp": 2.0, "xray": 1e-7, "sep_pfu": 0.5}


def _x_flare_storm() -> dict:
    return {"kp": 7.5, "xray": 5e-4, "sep_pfu": 800.0}


def test_stream_emits_well_formed_samples():
    stream = TelemetryStream(["44737", "48276"])
    out = stream.tick(weather=_nominal_weather())
    assert set(out.keys()) == {"44737", "48276"}
    s = out["44737"]
    assert s.sat_id == "44737"
    assert 200.0 <= s.current_mA <= 1500.0, f"unexpected current_mA {s.current_mA}"
    assert 2.5 <= s.voltage_V <= 3.6, f"unexpected voltage_V {s.voltage_V}"
    assert s.seu_bit_error_rate >= 0.0
    assert s.regime_hint in {"nominal", "tid", "see", "dielectric_charge"}


def test_buffer_grows_then_caps_at_window_samples():
    stream = TelemetryStream(["44737"])
    for _ in range(WINDOW_SAMPLES + 50):
        stream.tick(weather=_nominal_weather())
    win = stream.window("44737")
    assert len(win) == WINDOW_SAMPLES


def test_storm_weather_eventually_produces_see_or_tid_hint():
    """Under sustained storm conditions, the regime should NOT stay `nominal`
    forever. We tick a few thousand times and require at least one non-nominal
    sample to ensure the simulator actually responds to weather state."""
    stream = TelemetryStream(["44737"])
    non_nominal = 0
    for _ in range(3000):
        out = stream.tick(weather=_x_flare_storm())
        if out["44737"].regime_hint != "nominal":
            non_nominal += 1
    assert non_nominal > 0, "expected at least one non-nominal sample under storm conditions"


def test_telemetry_buffer_for_extracts_metric():
    stream = TelemetryStream(["44737"])
    for _ in range(64):
        stream.tick(weather=_nominal_weather())
    series = telemetry_buffer_for(stream, "44737", "current_mA")
    assert len(series) == 64
    assert all(isinstance(x, float) for x in series)


def test_unknown_metric_raises():
    stream = TelemetryStream(["44737"])
    stream.tick(weather=_nominal_weather())
    try:
        telemetry_buffer_for(stream, "44737", "unknown_metric")
    except ValueError as e:
        assert "unknown_metric" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown metric")
