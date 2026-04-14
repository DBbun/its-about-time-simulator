# =============================================================================
# DBbun LLC — Executable Publication Layer
# Tool      : paper_to_simulator_builder  v3.4.0
# Generated : 2026-04-14T00:21:32.919071Z
# Run ID    : bf578196-7ad2-4dd3-8406-fde3493c4db8
#
# © 2024-2025 DBbun LLC. All rights reserved.  |  dbbun.com
# CAGE: 16VU3  |  UEI: QY39Y38E6WG8  |  Cambridge, MA, USA
#
# This simulator, synthetic datasets, and all derived intellectual property
# are the exclusive property of DBbun LLC.  Unauthorised reproduction,
# distribution, or commercial use is prohibited without prior written consent.
# =============================================================================
#
"""
Integer Timestamp Overflow Simulator
=====================================
Simulates the NTP 32-bit seconds wrap-around (February 6, 2036) and the
UNIX 32-bit signed integer epoch overflow (January 19, 2038), as described in:

  "It's about Time — Cerf's Up, Communications of the ACM, April 2026"
  by Vinton G. Cerf

This simulator models counter accumulation, overflow events, misinterpretation
errors, and legacy device vulnerability fractions under multiple patching scenarios.
"""

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# =============================================================================
# MODEL PROFILE
# =============================================================================
MODEL_PROFILE = {
    "title": "It's about Time — Cerf's Up, Communications of the ACM, April 2026",
    "domain": "Integer timestamp overflow hazards in NTP and UNIX legacy systems",
    "parameters": {
        "ntp_max_counter":                   {"value": 4294967295.0,   "unit": "seconds",       "source": "extracted", "description": "Maximum value of 32-bit unsigned NTP seconds counter (2^32 - 1)"},
        "ntp_epoch_year":                    {"value": 1900.0,         "unit": "year",          "source": "extracted", "description": "NTP epoch start year: January 1, 1900"},
        "ntp_wraparound_year":               {"value": 2036.1,         "unit": "year",          "source": "extracted", "description": "Calendar year of NTP 32-bit overflow: February 6, 2036"},
        "ntp_wraparound_seconds_from_epoch": {"value": 4294967296.0,   "unit": "seconds",       "source": "extracted", "description": "Seconds from Jan 1 1900 at which NTP 32-bit counter wraps"},
        "unix_max_counter":                  {"value": 2147483647.0,   "unit": "seconds",       "source": "extracted", "description": "Maximum value of 32-bit signed UNIX integer (2^31 - 1)"},
        "unix_epoch_year":                   {"value": 1970.0,         "unit": "year",          "source": "extracted", "description": "UNIX epoch start year: January 1, 1970"},
        "unix_wraparound_year":              {"value": 2038.05,        "unit": "year",          "source": "extracted", "description": "Calendar year of UNIX 32-bit signed overflow: January 19, 2038"},
        "unix_wraparound_seconds_from_epoch":{"value": 2147483647.0,   "unit": "seconds",       "source": "extracted", "description": "Seconds from Jan 1 1970 at which UNIX 32-bit counter hits max"},
        "unix_post_overflow_interpreted_year":{"value": 1901.89,       "unit": "year",          "source": "extracted", "description": "Year that post-overflow UNIX counter is misinterpreted as: Dec 13, 1901"},
        "ntp_post_overflow_interpreted_year": {"value": 1900.0,        "unit": "year",          "source": "extracted", "description": "Year that post-overflow NTP counter is misinterpreted as: Jan 1, 1900"},
        "unix_64bit_max_years":              {"value": 292000000000.0, "unit": "years",         "source": "extracted", "description": "Duration before 64-bit UNIX counter overflows (~292 billion years)"},
        "patch_rate_per_year":               {"value": 0.05,           "unit": "fraction/year", "source": "assumed",   "description": "Annual fraction of legacy/IoT devices upgraded from 32-bit to 64-bit"},
        "initial_legacy_fraction":           {"value": 0.4,            "unit": "fraction",      "source": "assumed",   "description": "Fraction of deployed embedded/IoT systems still using 32-bit time at start"},
        "seconds_per_year":                  {"value": 31557600.0,     "unit": "seconds/year",  "source": "extracted", "description": "Approximate seconds per Julian year (365.25 days)"},
        "simulation_start_year":             {"value": 2024.0,         "unit": "year",          "source": "assumed",   "description": "Start of the simulation timeline"},
        "simulation_end_year":               {"value": 2050.0,         "unit": "year",          "source": "assumed",   "description": "End of the simulation timeline"},
        "time_step_days":                    {"value": 30.0,           "unit": "days",          "source": "assumed",   "description": "Simulation time step in days (monthly resolution)"},
    },
    "scenarios": [
        {
            "label": "no_patch_legacy_only",
            "description": "All legacy 32-bit systems remain unpatched through 2050.",
            "param_overrides": {"patch_rate_per_year": 0.0, "initial_legacy_fraction": 1.0},
            "ntp_era_aware": False,
        },
        {
            "label": "slow_patch_baseline",
            "description": "Realistic baseline: 5% annual patch rate starting in 2024.",
            "param_overrides": {"patch_rate_per_year": 0.05, "initial_legacy_fraction": 0.40},
            "ntp_era_aware": False,
        },
        {
            "label": "aggressive_patch_campaign",
            "description": "Aggressive patching: 20% annual remediation rate.",
            "param_overrides": {"patch_rate_per_year": 0.20, "initial_legacy_fraction": 0.40},
            "ntp_era_aware": False,
        },
        {
            "label": "ntp_era_aware_systems",
            "description": "NTPv4 era awareness handles 2036 gracefully; UNIX 2038 still unaddressed.",
            "param_overrides": {"patch_rate_per_year": 0.05, "initial_legacy_fraction": 0.40},
            "ntp_era_aware": True,
        },
        {
            "label": "high_legacy_slow_patch",
            "description": "High legacy concentration (70%) with very slow patch rate (2%).",
            "param_overrides": {"patch_rate_per_year": 0.02, "initial_legacy_fraction": 0.70},
            "ntp_era_aware": False,
        },
    ],
}

# =============================================================================
# CONSTANTS
# =============================================================================
NTP_EPOCH_YEAR    = 1900.0
UNIX_EPOCH_YEAR   = 1970.0
SECONDS_PER_YEAR  = 31557600.0       # Julian year = 365.25 days
NTP_MAX_U32       = 2**32            # 4294967296
UNIX_MAX_S32      = 2**31 - 1        # 2147483647
UNIX_MIN_S32      = -(2**31)         # -2147483648
NTP_WRAPAROUND_YEAR  = NTP_EPOCH_YEAR  + NTP_MAX_U32 / SECONDS_PER_YEAR   # ~2036.09
UNIX_WRAPAROUND_YEAR = UNIX_EPOCH_YEAR + UNIX_MAX_S32 / SECONDS_PER_YEAR  # ~2038.04
SIM_START_YEAR    = 2024.0
SIM_END_YEAR      = 2050.0
TIME_STEP_DAYS    = 30.0
TIME_STEP_YEARS   = TIME_STEP_DAYS / 365.25

SCENARIO_COLORS = {
    "no_patch_legacy_only":      "#d62728",
    "slow_patch_baseline":       "#1f77b4",
    "aggressive_patch_campaign": "#2ca02c",
    "ntp_era_aware_systems":     "#9467bd",
    "high_legacy_slow_patch":    "#ff7f0e",
}

# =============================================================================
# SIMULATION CORE
# =============================================================================

def run_scenario(scenario: Dict[str, Any], scenario_index: int) -> List[Dict[str, Any]]:
    """Run one scenario and return list of row dicts."""
    np.random.seed(scenario_index)

    # Extract parameters with overrides
    overrides = scenario.get("param_overrides", {})
    patch_rate        = float(overrides.get("patch_rate_per_year",   0.05))
    init_legacy_frac  = float(overrides.get("initial_legacy_fraction", 0.4))
    ntp_era_aware     = bool(scenario.get("ntp_era_aware", False))
    label             = scenario["label"]

    # Build time grid
    years = np.arange(
        SIM_START_YEAR,
        SIM_END_YEAR + TIME_STEP_YEARS,
        TIME_STEP_YEARS
    )

    # State variables
    ntp_overflow_occurred  = False
    unix_overflow_occurred = False
    ntp_era_count          = 0

    rows: List[Dict[str, Any]] = []

    for year in years:
        # Clamp year to valid range
        year = float(np.clip(year, 1970.0, 2100.0))

        # ── TRUE elapsed seconds ─────────────────────────────────────────────
        true_sec_ntp  = (year - NTP_EPOCH_YEAR)  * SECONDS_PER_YEAR
        true_sec_unix = (year - UNIX_EPOCH_YEAR) * SECONDS_PER_YEAR

        # ── NTP 32-bit UNSIGNED counter ──────────────────────────────────────
        ntp_raw = true_sec_ntp % NTP_MAX_U32    # modular wrap-around
        ntp_raw = float(np.clip(ntp_raw, 0.0, 4294967295.0))

        # Detect first NTP overflow crossing
        if (not ntp_overflow_occurred) and (year >= NTP_WRAPAROUND_YEAR):
            ntp_overflow_occurred = True
            if ntp_era_aware:
                ntp_era_count += 1
            # For legacy (non-era-aware): ntp_era_count stays at 0

        # Era-aware systems: keep counting eras for subsequent wraps
        # (second wrap at ~2172, outside our window, but structure is correct)
        if ntp_era_aware and ntp_overflow_occurred:
            era_val = 1  # only one wrap occurs in 2024-2050 window
        else:
            era_val = ntp_era_count

        era_val = float(np.clip(era_val, 0.0, 1000.0))

        # Legacy NTP interpretation (no era correction)
        interpreted_ntp_year = NTP_EPOCH_YEAR + (ntp_raw / SECONDS_PER_YEAR)
        interpreted_ntp_year = float(np.clip(interpreted_ntp_year, 1900.0, 2106.0))

        # ── UNIX 32-bit SIGNED counter ───────────────────────────────────────
        unix_overflow_now = False
        if true_sec_unix <= UNIX_MAX_S32:
            unix_s32_raw     = int(true_sec_unix)
            unix_overflow_now = False
        else:
            # Signed overflow: subtract 2^32 to simulate wrap to negative
            unix_s32_raw     = int(true_sec_unix) - int(2**32)
            unix_overflow_now = True
            if not unix_overflow_occurred:
                unix_overflow_occurred = True

        unix_s32_raw = int(np.clip(unix_s32_raw, UNIX_MIN_S32, UNIX_MAX_S32))

        # Naive interpretation of signed 32-bit counter
        interpreted_unix_year = UNIX_EPOCH_YEAR + (unix_s32_raw / SECONDS_PER_YEAR)
        interpreted_unix_year = float(np.clip(interpreted_unix_year, 1901.0, 2106.0))

        # ── 64-bit counter (no overflow in window) ───────────────────────────
        unix_64bit_raw = int(true_sec_unix)
        unix_64bit_raw = int(np.clip(unix_64bit_raw, 0, int(9.223372036854776e18)))
        interpreted_unix_year_64bit = UNIX_EPOCH_YEAR + (unix_64bit_raw / SECONDS_PER_YEAR)
        interpreted_unix_year_64bit = float(np.clip(interpreted_unix_year_64bit, 1970.0, 2100.0))

        # ── TIME ERRORS ──────────────────────────────────────────────────────
        if ntp_overflow_occurred:
            time_error_ntp = abs(year - interpreted_ntp_year) * SECONDS_PER_YEAR
        else:
            time_error_ntp = 0.0
        time_error_ntp = float(np.clip(time_error_ntp, 0.0, 4294967295.0))

        if unix_overflow_occurred:
            time_error_unix = abs(year - interpreted_unix_year) * SECONDS_PER_YEAR
        else:
            time_error_unix = 0.0
        time_error_unix = float(np.clip(time_error_unix, 0.0, 4294967295.0))

        # ── OVERFLOW EVENT FLAG ──────────────────────────────────────────────
        ntp_event_this_step = (
            year >= NTP_WRAPAROUND_YEAR and
            year < NTP_WRAPAROUND_YEAR + TIME_STEP_YEARS
        )
        overflow_event_flag = 1 if (unix_overflow_now or ntp_event_this_step) else 0

        # ── LEGACY DEVICE FRACTION ───────────────────────────────────────────
        years_since_sim_start = max(0.0, year - SIM_START_YEAR)
        legacy_frac = init_legacy_frac * math.exp(-patch_rate * years_since_sim_start)
        legacy_frac = float(np.clip(legacy_frac, 0.0, 1.0))

        # ── RECORD ROW ───────────────────────────────────────────────────────
        row = {
            "simulation_year":              round(year, 6),
            "scenario_label":               label,
            "ntp_seconds_counter":          float(ntp_raw),
            "unix_signed_counter":          float(unix_s32_raw),
            "unix_64bit_counter":           float(unix_64bit_raw),
            "ntp_era":                      float(era_val),
            "interpreted_ntp_year":         float(interpreted_ntp_year),
            "interpreted_unix_year":        float(interpreted_unix_year),
            "interpreted_unix_year_64bit":  float(interpreted_unix_year_64bit),
            "overflow_event_flag":          int(overflow_event_flag),
            "ntp_overflow_occurred":        int(ntp_overflow_occurred),
            "unix_overflow_occurred":       int(unix_overflow_occurred),
            "time_error_ntp_seconds":       float(time_error_ntp),
            "time_error_unix_seconds":      float(time_error_unix),
            "legacy_device_fraction_affected": float(legacy_frac),
            "patch_rate_per_year":          float(patch_rate),
            "initial_legacy_fraction":      float(init_legacy_frac),
            "true_seconds_since_ntp_epoch": float(true_sec_ntp),
            "true_seconds_since_unix_epoch":float(true_sec_unix),
        }
        rows.append(row)

    return rows


def run_all_scenarios() -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Run all scenarios and return combined rows + per-scenario dict."""
    all_rows: List[Dict[str, Any]] = []
    scenario_rows: Dict[str, List[Dict[str, Any]]] = {}

    for idx, scenario in enumerate(MODEL_PROFILE["scenarios"]):
        rows = run_scenario(scenario, idx)
        scenario_rows[scenario["label"]] = rows
        all_rows.extend(rows)

    return all_rows, scenario_rows


# =============================================================================
# HEATMAP DATA
# =============================================================================

def compute_heatmap_data() -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute vulnerability heatmap over (init_frac, patch_rate) grid."""
    init_fracs  = np.linspace(0.1, 1.0, 10)
    patch_rates = np.linspace(0.01, 0.25, 10)

    years_to_2036 = 2036.09 - SIM_START_YEAR
    years_to_2038 = 2038.04 - SIM_START_YEAR

    heatmap_2036 = np.zeros((len(init_fracs), len(patch_rates)))
    heatmap_2038 = np.zeros((len(init_fracs), len(patch_rates)))

    for i, init_frac in enumerate(init_fracs):
        for j, p_rate in enumerate(patch_rates):
            heatmap_2036[i, j] = init_frac * math.exp(-p_rate * years_to_2036)
            heatmap_2038[i, j] = init_frac * math.exp(-p_rate * years_to_2038)

    return init_fracs, patch_rates, heatmap_2036, heatmap_2038


# =============================================================================
# CSV WRITERS
# =============================================================================

DATASET_SCHEMA = [
    "simulation_year", "scenario_label", "ntp_seconds_counter",
    "unix_signed_counter", "unix_64bit_counter", "ntp_era",
    "interpreted_ntp_year", "interpreted_unix_year", "interpreted_unix_year_64bit",
    "overflow_event_flag", "ntp_overflow_occurred", "unix_overflow_occurred",
    "time_error_ntp_seconds", "time_error_unix_seconds",
    "legacy_device_fraction_affected", "patch_rate_per_year",
    "initial_legacy_fraction", "true_seconds_since_ntp_epoch",
    "true_seconds_since_unix_epoch",
]


def write_simulation_outputs(all_rows: List[Dict[str, Any]], out_dir: Path) -> None:
    """Write simulation_outputs.csv — one row per timestep × scenario."""
    if not all_rows:
        print("WARNING: No simulation rows to write.")
        return
    out_path = out_dir / "simulation_outputs.csv"
    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=DATASET_SCHEMA)
            writer.writeheader()
            for row in all_rows:
                writer.writerow({k: row[k] for k in DATASET_SCHEMA})
        print(f"  Wrote {out_path}")
    except Exception as e:
        print(f"WARNING: Failed to write simulation_outputs.csv: {e}")


def write_scenario_summary(
    scenario_rows: Dict[str, List[Dict[str, Any]]],
    out_dir: Path
) -> None:
    """Write scenario_summary.csv — one row per scenario with aggregate metrics."""
    numeric_vars = [
        "ntp_seconds_counter", "unix_signed_counter", "unix_64bit_counter",
        "ntp_era", "interpreted_ntp_year", "interpreted_unix_year",
        "overflow_event_flag", "time_error_ntp_seconds", "time_error_unix_seconds",
        "legacy_device_fraction_affected",
    ]

    summary_rows = []
    for label, rows in scenario_rows.items():
        if not rows:
            continue
        summary = {"scenario_label": label}
        # Patch params from first row
        summary["patch_rate_per_year"]    = rows[0]["patch_rate_per_year"]
        summary["initial_legacy_fraction"] = rows[0]["initial_legacy_fraction"]
        summary["n_steps"]                = len(rows)
        summary["ntp_overflow_steps"]     = sum(r["ntp_overflow_occurred"] for r in rows)
        summary["unix_overflow_steps"]    = sum(r["unix_overflow_occurred"] for r in rows)
        summary["overflow_events_total"]  = sum(r["overflow_event_flag"] for r in rows)

        for var in numeric_vars:
            vals = np.array([r[var] for r in rows], dtype=float)
            summary[f"{var}_mean"] = float(np.mean(vals))
            summary[f"{var}_std"]  = float(np.std(vals))
            summary[f"{var}_min"]  = float(np.min(vals))
            summary[f"{var}_max"]  = float(np.max(vals))

        # KPI: fraction of devices unpatched at 2036 and 2038
        rows_at_2036 = [r for r in rows if abs(r["simulation_year"] - 2036.09) < TIME_STEP_YEARS]
        rows_at_2038 = [r for r in rows if abs(r["simulation_year"] - 2038.04) < TIME_STEP_YEARS]
        summary["legacy_frac_at_2036"] = rows_at_2036[0]["legacy_device_fraction_affected"] if rows_at_2036 else 0.0
        summary["legacy_frac_at_2038"] = rows_at_2038[0]["legacy_device_fraction_affected"] if rows_at_2038 else 0.0
        summary["max_time_error_ntp_seconds"]  = float(max(r["time_error_ntp_seconds"]  for r in rows))
        summary["max_time_error_unix_seconds"] = float(max(r["time_error_unix_seconds"] for r in rows))

        summary_rows.append(summary)

    if not summary_rows:
        print("WARNING: No summary rows to write.")
        return

    fieldnames = list(summary_rows[0].keys())
    out_path = out_dir / "scenario_summary.csv"
    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"  Wrote {out_path}")
    except Exception as e:
        print(f"WARNING: Failed to write scenario_summary.csv: {e}")


def write_parameters_used(out_dir: Path) -> None:
    """Write parameters_used.csv — one row per parameter."""
    out_path = out_dir / "parameters_used.csv"
    params = MODEL_PROFILE["parameters"]
    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "value", "unit", "source", "description"])
            writer.writeheader()
            for name, info in params.items():
                writer.writerow({
                    "name":        name,
                    "value":       info["value"],
                    "unit":        info["unit"],
                    "source":      info["source"],
                    "description": info["description"],
                })
        print(f"  Wrote {out_path}")
    except Exception as e:
        print(f"WARNING: Failed to write parameters_used.csv: {e}")


def write_summary_json(
    all_rows: List[Dict[str, Any]],
    scenario_rows: Dict[str, List[Dict[str, Any]]],
    out_dir: Path
) -> None:
    """Write summary.json with key aggregate metrics."""
    summary = {
        "title": MODEL_PROFILE["title"],
        "total_simulation_rows": len(all_rows),
        "n_scenarios": len(scenario_rows),
        "ntp_wraparound_year":  round(NTP_WRAPAROUND_YEAR, 4),
        "unix_wraparound_year": round(UNIX_WRAPAROUND_YEAR, 4),
        "ntp_overflow_error_seconds": round(NTP_MAX_U32 / SECONDS_PER_YEAR * SECONDS_PER_YEAR, 0),
        "unix_overflow_error_seconds": round((UNIX_MAX_S32 + 2**31) / SECONDS_PER_YEAR * SECONDS_PER_YEAR, 0),
        "scenarios": {},
    }
    for label, rows in scenario_rows.items():
        if not rows:
            continue
        max_ntp_err  = max(r["time_error_ntp_seconds"]  for r in rows)
        max_unix_err = max(r["time_error_unix_seconds"] for r in rows)
        frac_final   = rows[-1]["legacy_device_fraction_affected"]
        summary["scenarios"][label] = {
            "patch_rate_per_year":      rows[0]["patch_rate_per_year"],
            "initial_legacy_fraction":  rows[0]["initial_legacy_fraction"],
            "max_time_error_ntp_sec":   round(max_ntp_err, 0),
            "max_time_error_unix_sec":  round(max_unix_err, 0),
            "legacy_frac_at_end_2050":  round(frac_final, 6),
        }

    out_path = out_dir / "summary.json"
    try:
        with open(out_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"  Wrote {out_path}")
    except Exception as e:
        print(f"WARNING: Failed to write summary.json: {e}")


# =============================================================================
# FIGURE GENERATORS
# =============================================================================

def _vlines_2036_2038(ax, alpha: float = 0.6) -> None:
    ax.axvline(x=NTP_WRAPAROUND_YEAR,  color="darkorange", linestyle="--", linewidth=1.5,
               alpha=alpha, label="NTP wrap 2036")
    ax.axvline(x=UNIX_WRAPAROUND_YEAR, color="crimson",    linestyle="--", linewidth=1.5,
               alpha=alpha, label="UNIX wrap 2038")


def fig1_ntp_counter(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """NTP 32-bit Counter Accumulation and Wrap-Around."""
    try:
        label = "no_patch_legacy_only"
        rows = scenario_rows.get(label, [])
        if not rows:
            print("WARNING fig1: No rows for no_patch_legacy_only")
            return

        years      = np.array([r["simulation_year"]        for r in rows])
        ntp_vals   = np.array([r["ntp_seconds_counter"]     for r in rows])
        unix64_vals= np.array([r["true_seconds_since_ntp_epoch"] for r in rows])
        assert len(years) == len(ntp_vals) == len(unix64_vals), "fig1 array length mismatch"

        if len(years) == 0:
            print("WARNING fig1: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(years, ntp_vals,    color="steelblue", linewidth=2, label="NTP 32-bit counter (wraps at 2036)")
        ax.plot(years, unix64_vals, color="green",     linewidth=2, linestyle="--", label="64-bit equivalent (no wrap)")
        _vlines_2036_2038(ax)
        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("Counter Value (seconds)")
        ax.set_title("NTP 32-bit Counter Accumulation and Wrap-Around (2024–2050)")
        ax.legend(loc="upper left")
        ax.yaxis.get_major_formatter().set_scientific(False)
        plt.tight_layout()
        out_path = out_dir / "fig1_ntp_counter.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig1 failed: {e}")


def fig2_unix_signed_counter(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """UNIX 32-bit Signed Counter and Year 2038 Overflow."""
    try:
        label = "no_patch_legacy_only"
        rows = scenario_rows.get(label, [])
        if not rows:
            print("WARNING fig2: No rows")
            return

        years      = np.array([r["simulation_year"]         for r in rows])
        unix32     = np.array([r["unix_signed_counter"]      for r in rows])
        unix64     = np.array([r["true_seconds_since_unix_epoch"] for r in rows])
        assert len(years) == len(unix32) == len(unix64), "fig2 array length mismatch"

        if len(years) == 0:
            print("WARNING fig2: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(years, unix32, color="crimson",  linewidth=2, label="UNIX 32-bit signed (overflows 2038)")
        ax.plot(years, unix64, color="navy",     linewidth=2, linestyle="--", label="64-bit equivalent (no overflow)")
        _vlines_2036_2038(ax)
        ax.axhline(y=0, color="gray", linestyle=":", linewidth=1)
        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("Counter Value (seconds)")
        ax.set_title("UNIX 32-bit Signed Counter and Year 2038 Overflow")
        ax.legend(loc="upper left")
        plt.tight_layout()
        out_path = out_dir / "fig2_unix_counter.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig2 failed: {e}")


def fig3_interpreted_unix_year(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """Misinterpreted Calendar Year After UNIX 2038 Overflow."""
    try:
        label = "no_patch_legacy_only"
        rows = scenario_rows.get(label, [])
        if not rows:
            print("WARNING fig3: No rows")
            return

        years        = np.array([r["simulation_year"]        for r in rows])
        interp_unix  = np.array([r["interpreted_unix_year"]   for r in rows])
        true_year    = np.array([r["interpreted_unix_year_64bit"] for r in rows])
        assert len(years) == len(interp_unix) == len(true_year), "fig3 array length mismatch"

        if len(years) == 0:
            print("WARNING fig3: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(years, true_year,   color="navy",   linewidth=2, linestyle="--", label="True calendar year")
        ax.plot(years, interp_unix, color="crimson", linewidth=2, label="32-bit interpreted year")
        ax.axhline(y=1901.95, color="darkorange", linestyle=":", linewidth=1.5, label="Dec 13, 1901 reference")
        _vlines_2036_2038(ax)
        ax.set_xlabel("True Calendar Year")
        ax.set_ylabel("Interpreted Calendar Year")
        ax.set_title("Misinterpreted Calendar Year After UNIX 2038 Overflow")
        ax.legend(loc="upper left")
        plt.tight_layout()
        out_path = out_dir / "fig3_interpreted_unix_year.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig3 failed: {e}")


def fig4_time_error(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """Time Interpretation Error (seconds) for 32-bit Systems Post-Overflow."""
    try:
        label = "no_patch_legacy_only"
        rows = scenario_rows.get(label, [])
        if not rows:
            print("WARNING fig4: No rows")
            return

        years    = np.array([r["simulation_year"]         for r in rows])
        err_ntp  = np.array([r["time_error_ntp_seconds"]  for r in rows])
        err_unix = np.array([r["time_error_unix_seconds"] for r in rows])
        assert len(years) == len(err_ntp) == len(err_unix), "fig4 array length mismatch"

        if len(years) == 0:
            print("WARNING fig4: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(years, err_ntp,  color="darkorange", linewidth=2, label="NTP 32-bit error (seconds)")
        ax.plot(years, err_unix, color="crimson",    linewidth=2, label="UNIX 32-bit error (seconds)")
        _vlines_2036_2038(ax)
        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("Absolute Time Error (seconds)")
        ax.set_title("Time Interpretation Error (seconds) for 32-bit Systems Post-Overflow")
        ax.legend(loc="upper left")
        ax.yaxis.get_major_formatter().set_scientific(False)
        plt.tight_layout()
        out_path = out_dir / "fig4_time_error.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig4 failed: {e}")


def fig5_legacy_fraction(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """Fraction of Unpatched Legacy/IoT Devices Under Different Patch Scenarios."""
    try:
        fig, ax = plt.subplots(figsize=(10, 5))

        for label, rows in scenario_rows.items():
            if not rows:
                continue
            years = np.array([r["simulation_year"]                for r in rows])
            frac  = np.array([r["legacy_device_fraction_affected"] for r in rows])
            assert len(years) == len(frac), f"fig5 array mismatch for {label}"
            if len(years) == 0:
                continue
            color = SCENARIO_COLORS.get(label, "gray")
            ax.plot(years, frac, color=color, linewidth=2, label=label)

        _vlines_2036_2038(ax)
        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("Fraction of Unpatched Devices")
        ax.set_title("Fraction of Unpatched Legacy/IoT Devices Under Different Patch Scenarios")
        ax.set_ylim(0.0, 1.05)
        ax.legend(loc="upper right", fontsize=8)
        plt.tight_layout()
        out_path = out_dir / "fig5_legacy_fraction.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig5 failed: {e}")


def fig6_overflow_events(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """Overflow Event Timeline: NTP 2036 and UNIX 2038."""
    try:
        label = "no_patch_legacy_only"
        rows = scenario_rows.get(label, [])
        if not rows:
            print("WARNING fig6: No rows")
            return

        years = np.array([r["simulation_year"]    for r in rows])
        flags = np.array([r["overflow_event_flag"] for r in rows])
        assert len(years) == len(flags), "fig6 array length mismatch"

        if len(years) == 0:
            print("WARNING fig6: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 4))

        # Plot all points (0s as small dots, 1s as big markers)
        mask0 = flags == 0
        mask1 = flags == 1

        ax.scatter(years[mask0], flags[mask0], c="steelblue", s=10, alpha=0.4, label="No overflow")
        if np.any(mask1):
            ax.scatter(years[mask1], flags[mask1], c="crimson", s=200, zorder=5, label="Overflow event")

        # Annotate specific events
        ax.annotate(
            "NTP 32-bit Wrap\nFeb 6, 2036\n→ misreads as Jan 1, 1900",
            xy=(NTP_WRAPAROUND_YEAR, 1),
            xytext=(NTP_WRAPAROUND_YEAR - 3, 0.6),
            arrowprops=dict(arrowstyle="->", color="darkorange"),
            fontsize=8, color="darkorange"
        )
        ax.annotate(
            "UNIX 32-bit Overflow\nJan 19, 2038 03:14:07 UTC\n→ misreads as Dec 13, 1901",
            xy=(UNIX_WRAPAROUND_YEAR, 1),
            xytext=(UNIX_WRAPAROUND_YEAR + 0.5, 0.6),
            arrowprops=dict(arrowstyle="->", color="crimson"),
            fontsize=8, color="crimson"
        )

        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("Overflow Event Flag")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Normal (0)", "Overflow (1)"])
        ax.set_title("Overflow Event Timeline: NTP 2036 and UNIX 2038")
        ax.legend(loc="upper left")
        plt.tight_layout()
        out_path = out_dir / "fig6_overflow_events.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig6 failed: {e}")


def fig7_heatmap(out_dir: Path) -> None:
    """Vulnerability Heatmap: Legacy Device Exposure at 2036 and 2038 Events."""
    try:
        init_fracs, patch_rates, hm_2036, hm_2038 = compute_heatmap_data()

        if hm_2036.size == 0 or hm_2038.size == 0:
            print("WARNING fig7: Empty heatmap data")
            return

        fig, axes = plt.subplots(1, 2, figsize=(13, 5))

        for ax, hm, event_year, title_suffix in [
            (axes[0], hm_2036, 2036, "NTP Overflow 2036"),
            (axes[1], hm_2038, 2038, "UNIX Overflow 2038"),
        ]:
            im = ax.imshow(
                hm,
                aspect="auto",
                origin="lower",
                cmap="RdYlGn_r",
                vmin=0.0, vmax=1.0,
                extent=[patch_rates[0], patch_rates[-1], init_fracs[0], init_fracs[-1]],
            )
            plt.colorbar(im, ax=ax, label="Unpatched Fraction")
            ax.set_xlabel("Annual Patch Rate (fraction/year)")
            ax.set_ylabel("Initial Legacy Fraction")
            ax.set_title(f"Vulnerability at {event_year}: {title_suffix}")

        fig.suptitle("Vulnerability Heatmap: Legacy Device Exposure at 2036 and 2038 Events", fontsize=11)
        plt.tight_layout()
        out_path = out_dir / "fig7_heatmap.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig7 failed: {e}")


def fig8_ntp_era(scenario_rows: Dict[str, List[Dict[str, Any]]], out_dir: Path) -> None:
    """NTP Era Number vs Calendar Year (Era-Aware vs Legacy Systems)."""
    try:
        # Era-aware scenario
        label_aware  = "ntp_era_aware_systems"
        label_legacy = "no_patch_legacy_only"

        rows_aware  = scenario_rows.get(label_aware,  [])
        rows_legacy = scenario_rows.get(label_legacy, [])

        if not rows_aware or not rows_legacy:
            print("WARNING fig8: Missing rows for one or both scenarios")
            return

        years_aware  = np.array([r["simulation_year"] for r in rows_aware])
        era_aware    = np.array([r["ntp_era"]          for r in rows_aware])
        years_legacy = np.array([r["simulation_year"]  for r in rows_legacy])
        era_legacy   = np.array([r["ntp_era"]           for r in rows_legacy])

        assert len(years_aware)  == len(era_aware),  "fig8 era_aware length mismatch"
        assert len(years_legacy) == len(era_legacy), "fig8 era_legacy length mismatch"

        if len(years_aware) == 0 or len(years_legacy) == 0:
            print("WARNING fig8: Empty arrays")
            return

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.step(years_aware,  era_aware,  where="post", color="green",  linewidth=2, label="Era-aware NTPv4 (era increments at 2036)")
        ax.step(years_legacy, era_legacy, where="post", color="crimson", linewidth=2, linestyle="--", label="Legacy NTP (era stays 0 → misinterpretation)")
        _vlines_2036_2038(ax)
        ax.annotate(
            "NTPv4 era increments\nto 1 at 2036 wrap",
            xy=(NTP_WRAPAROUND_YEAR, 1),
            xytext=(NTP_WRAPAROUND_YEAR + 1, 0.7),
            arrowprops=dict(arrowstyle="->", color="green"),
            fontsize=8, color="green"
        )
        ax.set_xlabel("Calendar Year")
        ax.set_ylabel("NTP Era Number")
        ax.set_title("NTP Era Number vs Calendar Year (Era-Aware vs Legacy Systems)")
        ax.set_yticks([0, 1])
        ax.legend(loc="center left")
        plt.tight_layout()
        out_path = out_dir / "fig8_ntp_era.png"
        plt.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except Exception as e:
        print(f"WARNING fig8 failed: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Integer Timestamp Overflow Simulator (NTP 2036 / UNIX 2038)"
    )
    parser.add_argument(
        "--output", type=str, default="./sim_outputs",
        help="Output directory for figures, CSVs, and JSON (default: ./sim_outputs)"
    )
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir.resolve()}")

    # ── Run simulations ────────────────────────────────────────────────────
    print("\nRunning simulations...")
    all_rows, scenario_rows = run_all_scenarios()
    print(f"  Total rows: {len(all_rows)}")
    for label, rows in scenario_rows.items():
        print(f"    {label}: {len(rows)} steps")

    # ── Write CSVs ─────────────────────────────────────────────────────────
    print("\nWriting CSV files...")
    write_simulation_outputs(all_rows, out_dir)
    write_scenario_summary(scenario_rows, out_dir)
    write_parameters_used(out_dir)

    # ── Write JSON ─────────────────────────────────────────────────────────
    print("\nWriting summary JSON...")
    write_summary_json(all_rows, scenario_rows, out_dir)

    # ── Generate figures ───────────────────────────────────────────────────
    print("\nGenerating figures...")
    fig1_ntp_counter(scenario_rows, out_dir)
    fig2_unix_signed_counter(scenario_rows, out_dir)
    fig3_interpreted_unix_year(scenario_rows, out_dir)
    fig4_time_error(scenario_rows, out_dir)
    fig5_legacy_fraction(scenario_rows, out_dir)
    fig6_overflow_events(scenario_rows, out_dir)
    fig7_heatmap(out_dir)
    fig8_ntp_era(scenario_rows, out_dir)

    print(f"\nDone. All outputs saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()