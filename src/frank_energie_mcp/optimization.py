"""Pure, timezone-aware optimization of normalized Frank Energie price intervals."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import isfinite, sqrt
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Amsterdam")


def positive(value: float, name: str, *, allow_zero: bool = False) -> float:
    """Reject nonfinite, boolean, and nonpositive numeric inputs."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}.")
    return float(value)


def validated_series(
    records: list[dict[str, Any]], day: date, resolution: str
) -> list[tuple[datetime, datetime, float]]:
    """Validate normalized intervals, chronological order and day boundaries."""
    step = {"PT15M": 900, "PT60M": 3600}[resolution]
    start = datetime(day.year, day.month, day.day, tzinfo=ZONE).astimezone(UTC)
    next_day = day + timedelta(days=1)
    end = datetime(
        next_day.year, next_day.month, next_day.day, tzinfo=ZONE
    ).astimezone(UTC)
    ordered = sorted(
        (
            datetime.fromisoformat(item["date_from"]).astimezone(UTC),
            datetime.fromisoformat(item["date_till"]).astimezone(UTC),
            float(item["total"]),
        )
        for item in records
    )
    previous: datetime | None = None
    for begin, finish, _ in ordered:
        if begin < start or finish > end or (finish - begin).total_seconds() != step:
            raise ValueError("Price intervals must fit the day and requested resolution.")
        if previous is not None and begin < previous:
            raise ValueError("Overlapping price intervals.")
        previous = finish
    return ordered


def windows(
    series: list[tuple[datetime, datetime, float]],
    duration_minutes: int,
    resolution: str,
    earliest: datetime | None = None,
    latest: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return only uninterrupted fixed-length windows within optional bounds."""
    step = {"PT15M": 15, "PT60M": 60}[resolution]
    if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
        raise ValueError("duration_minutes must be an integer.")
    if duration_minutes <= 0 or duration_minutes % step:
        raise ValueError("duration_minutes must be a positive multiple of resolution.")
    count = duration_minutes // step
    results: list[dict[str, Any]] = []
    for i in range(len(series) - count + 1):
        segment = series[i : i + count]
        if any(segment[j][1] != segment[j + 1][0] for j in range(count - 1)):
            continue
        start, end = segment[0][0], segment[-1][1]
        if earliest is not None and start < earliest:
            continue
        if latest is not None and end > latest:
            continue
        results.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "average_total": sum(entry[2] for entry in segment) / count,
                "interval_count": count,
            }
        )
    return results


def best_start(
    series: list[tuple[datetime, datetime, float]],
    duration_minutes: int,
    resolution: str,
    earliest: datetime | None = None,
    latest: datetime | None = None,
) -> dict[str, Any] | None:
    """Choose the cheapest full window; ties prefer earliest chronological start."""
    options = windows(series, duration_minutes, resolution, earliest, latest)
    return min(options, key=lambda item: item["average_total"], default=None)


def energy_cost(
    series: list[tuple[datetime, datetime, float]],
    start: datetime,
    duration_minutes: int,
    power_kw: float,
    resolution: str,
) -> dict[str, Any]:
    """Integrate constant electrical power over a fully covered window."""
    power = positive(power_kw, "power_kw")
    options = windows(series, duration_minutes, resolution, start, start + timedelta(minutes=duration_minutes))
    matching = next((item for item in options if datetime.fromisoformat(item["start"]) == start), None)
    if matching is None:
        return {"status": "incomplete", "cost": None, "energy_kwh": None}
    energy = power * duration_minutes / 60
    return {"status": "complete", "cost": matching["average_total"] * energy, "energy_kwh": energy}


def threshold_periods(
    series: list[tuple[datetime, datetime, float]],
    threshold: float,
    below: bool,
    minimum_minutes: int,
) -> list[dict[str, Any]]:
    """Group adjacent qualifying price intervals without bridging gaps."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not isfinite(threshold):
        raise ValueError("threshold must be finite.")
    if isinstance(minimum_minutes, bool) or not isinstance(minimum_minutes, int) or minimum_minutes <= 0:
        raise ValueError("minimum_minutes must be a positive integer.")
    groups: list[list[tuple[datetime, datetime, float]]] = []
    current: list[tuple[datetime, datetime, float]] = []
    for entry in series:
        qualifies = entry[2] < threshold if below else entry[2] > threshold
        if not qualifies:
            if current:
                groups.append(current)
            current = []
            continue
        if current and current[-1][1] != entry[0]:
            groups.append(current)
            current = []
        current.append(entry)
    if current:
        groups.append(current)
    return [
        {
            "start": group[0][0].isoformat(),
            "end": group[-1][1].isoformat(),
            "duration_minutes": int((group[-1][1] - group[0][0]).total_seconds() / 60),
            "average_total": sum(item[2] for item in group) / len(group),
        }
        for group in groups
        if (group[-1][1] - group[0][0]).total_seconds() >= minimum_minutes * 60
    ]


def split_periods(
    series: list[tuple[datetime, datetime, float]],
    total_minutes: int,
    minimum_block_minutes: int,
    resolution: str,
) -> dict[str, Any]:
    """Choose cheapest nonoverlapping fixed blocks, without partial allocations."""
    step = {"PT15M": 15, "PT60M": 60}[resolution]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value % step
        for value in (total_minutes, minimum_block_minutes)
    ) or total_minutes % minimum_block_minutes:
        raise ValueError("Durations must be positive resolution multiples and divisible.")
    blocks = windows(series, minimum_block_minutes, resolution)
    blocks.sort(key=lambda item: (item["average_total"], item["start"]))
    selected: list[dict[str, Any]] = []
    for block in blocks:
        start = datetime.fromisoformat(block["start"])
        end = datetime.fromisoformat(block["end"])
        if any(
            start < datetime.fromisoformat(item["end"])
            and end > datetime.fromisoformat(item["start"])
            for item in selected
        ):
            continue
        selected.append(block)
        if len(selected) == total_minutes // minimum_block_minutes:
            break
    if len(selected) != total_minutes // minimum_block_minutes:
        return {"status": "incomplete", "periods": [], "average_total": None}
    selected.sort(key=lambda item: item["start"])
    return {
        "status": "complete",
        "periods": selected,
        "average_total": sum(item["average_total"] for item in selected) / len(selected),
    }


def battery_savings(
    series: list[tuple[datetime, datetime, float]],
    capacity_kwh: float,
    charge_power_kw: float,
    discharge_power_kw: float,
    round_trip_efficiency: float,
    resolution: str,
) -> dict[str, Any]:
    """Estimate one charge/discharge cycle, with chronological power constraints."""
    capacity = positive(capacity_kwh, "capacity_kwh")
    charge = positive(charge_power_kw, "charge_power_kw")
    discharge = positive(discharge_power_kw, "discharge_power_kw")
    efficiency = positive(round_trip_efficiency, "round_trip_efficiency")
    if efficiency > 1:
        raise ValueError("round_trip_efficiency must be at most 1.")
    step = {"PT15M": 15, "PT60M": 60}[resolution]
    charge_minutes = int(-(-capacity * 60 // (charge * step))) * step
    discharge_minutes = int(-(-capacity * efficiency * 60 // (discharge * step))) * step
    charging = windows(series, charge_minutes, resolution)
    discharging = windows(series, discharge_minutes, resolution)
    best: dict[str, Any] | None = None
    for inbound in charging:
        for outbound in discharging:
            if inbound["end"] > outbound["start"]:
                continue
            cost = capacity * inbound["average_total"]
            revenue = capacity * efficiency * outbound["average_total"]
            savings = revenue - cost
            if best is None or savings > best["estimated_savings"]:
                best = {
                    "charge": inbound,
                    "discharge": outbound,
                    "estimated_savings": savings,
                    "charge_cost": cost,
                    "avoided_discharge_cost": revenue,
                }
    return {
        "status": "estimated" if best is not None else "insufficient_coverage",
        "cycle": best,
        "assumptions": "One idealized cycle; no fixed fees, battery degradation or load profile.",
    }


def price_statistics(
    series: list[tuple[datetime, datetime, float]],
) -> dict[str, Any]:
    """Compute descriptive population statistics of available total prices."""
    values = sorted(item[2] for item in series)
    if not values:
        return {
            "count": 0, "mean": None, "median": None, "minimum": None,
            "maximum": None, "range": None, "standard_deviation": None,
            "p25": None, "p75": None,
        }
    mean = sum(values) / len(values)

    def percentile(fraction: float) -> float:
        """Interpolate at a fractional index in the ordered values."""
        position = (len(values) - 1) * fraction
        lower = int(position)
        return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (
            position - lower
        )

    return {
        "count": len(values),
        "mean": mean,
        "median": median(values),
        "minimum": values[0],
        "maximum": values[-1],
        "range": values[-1] - values[0],
        "standard_deviation": sqrt(sum((value - mean) ** 2 for value in values) / len(values)),
        "p25": percentile(0.25),
        "p75": percentile(0.75),
    }


def price_volatility(
    series: list[tuple[datetime, datetime, float]],
) -> dict[str, Any]:
    """Describe spread and adjacent price changes without bridging missing intervals."""
    stats = price_statistics(series)
    differences = [
        series[i][2] - series[i - 1][2]
        for i in range(1, len(series))
        if series[i - 1][1] == series[i][0]
    ]
    return {
        **stats,
        "adjacent_change_count": len(differences),
        "largest_increase": max(differences, default=None),
        "largest_decrease": min(differences, default=None),
        "mean_absolute_change": (
            sum(abs(value) for value in differences) / len(differences)
            if differences else None
        ),
    }


def price_trend(
    series: list[tuple[datetime, datetime, float]],
    stable_tolerance: float,
) -> dict[str, Any]:
    """Classify endpoint change over available prices, reporting gaps explicitly."""
    tolerance = positive(stable_tolerance, "stable_tolerance", allow_zero=True)
    if len(series) < 2:
        return {"direction": "insufficient_data", "change": None, "has_gaps": False}
    change = series[-1][2] - series[0][2]
    gaps = any(series[i - 1][1] != series[i][0] for i in range(1, len(series)))
    direction = "stable" if abs(change) <= tolerance else (
        "rising" if change > 0 else "falling"
    )
    return {"direction": direction, "change": change, "has_gaps": gaps}
