"""
Sector Strength Engine V1
=========================

Drop-in replacement for the existing engine.sector_rotation module.

Design goals:
1. Preserve the existing public interface:
      - build_sector_rankings(results)
      - get_sector_strength(sector, sector_rankings)
2. Avoid any dependency on NSE classification or additional market-data calls.
3. Calculate sector strength ONLY after scanner results exist.
4. Preserve the existing downstream fields:
      Sector, Strength, Average Edge, Average Score,
      Average RS, Institutional, Stocks
5. Add transparent component metrics for diagnostics.
6. Do NOT feed sector strength back into scanner scoring in V1.
   This prevents circular scoring.

V1 component model:
    Average Edge       20%
    Average Score      20%
    Average RS         25%
    Institutional      20%
    Breadth            15%

All components are normalized to 0-100.

Breadth:
    BUY / STRONG_BUY / WATCH / SWING BUY / INSTITUTIONAL BUY
    participation among valid sector stocks.

Minimum valid stocks:
    1 stock is allowed, but the result is marked with
    Breadth Confidence = LOW.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Dict, Iterable, List


VERSION = "SECTOR_STRENGTH_V1"

WEIGHTS = {
    "Average Edge": 0.20,
    "Average Score": 0.20,
    "Average RS": 0.25,
    "Institutional": 0.20,
    "Breadth": 0.15,
}

BUY_ACTIONS = {
    "BUY",
    "STRONG_BUY",
    "SWING BUY",
    "INSTITUTIONAL BUY",
    "TACTICAL BUY",
    "ACCUMULATE",
}

WATCH_ACTIONS = {
    "WATCH",
    "WATCHLIST",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        if isinstance(value, bool):
            return float(value)

        number = float(value)

        if number != number:  # NaN
            return default

        return number

    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _round(value: float, digits: int = 2) -> float:
    return round(_clamp(value), digits)


def _normalize_edge(edge: float) -> float:
    """
    Edge rating is normally 0-9.
    Convert it to a 0-100 component.
    """
    return _clamp(edge * (100.0 / 9.0))


def _normalize_score(score: float) -> float:
    """
    Scanner score is normally 0-100.
    """
    return _clamp(score)


def _normalize_rs(rs: float) -> float:
    """
    RS score is expected to be approximately 0-100.
    """
    return _clamp(rs)


def _normalize_institutional(value: float) -> float:
    """
    Institutional rank is expected to be approximately 0-100.
    """
    return _clamp(value)


def _breadth_score(rows: Iterable[Dict[str, Any]]) -> float:
    """
    Sector breadth based on current scanner participation.

    BUY-type actions receive full participation credit.
    WATCH-type actions receive half credit.
    Other valid stocks receive zero.

    This is intentionally simple in V1. We can introduce
    EMA breadth / advancing-declining breadth / volume breadth
    in V2 without changing the public interface.
    """
    rows = list(rows)

    if not rows:
        return 0.0

    participating = 0.0

    for row in rows:
        action = _text(row.get("trade_action")).upper()
        signal = _text(row.get("signal")).upper()

        if action in {x.upper() for x in BUY_ACTIONS}:
            participating += 1.0
        elif action in {x.upper() for x in WATCH_ACTIONS}:
            participating += 0.5
        elif "BUY" in signal:
            participating += 0.75

    return _clamp((participating / len(rows)) * 100.0)


def _valid_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False

    sector = _text(
        row.get("sector", row.get("Sector", ""))
    )

    ticker = _text(
        row.get("ticker", row.get("Ticker", ""))
    )

    return bool(sector and ticker)


def _build_sector_record(
    sector: str,
    rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    edge_values = [
        _safe_float(row.get("edge_rating"))
        for row in rows
    ]

    score_values = [
        _safe_float(row.get("score"))
        for row in rows
    ]

    rs_values = [
        _safe_float(row.get("rs_score"))
        for row in rows
    ]

    institutional_values = [
        _safe_float(row.get("institutional_rank"))
        for row in rows
    ]

    avg_edge = mean(edge_values) if edge_values else 0.0
    avg_score = mean(score_values) if score_values else 0.0
    avg_rs = mean(rs_values) if rs_values else 0.0
    institutional = (
        mean(institutional_values)
        if institutional_values
        else 0.0
    )

    edge_component = _normalize_edge(avg_edge)
    score_component = _normalize_score(avg_score)
    rs_component = _normalize_rs(avg_rs)
    institutional_component = _normalize_institutional(
        institutional
    )
    breadth_component = _breadth_score(rows)

    strength = (
        edge_component * WEIGHTS["Average Edge"]
        + score_component * WEIGHTS["Average Score"]
        + rs_component * WEIGHTS["Average RS"]
        + institutional_component * WEIGHTS["Institutional"]
        + breadth_component * WEIGHTS["Breadth"]
    )

    if len(rows) >= 10:
        breadth_confidence = "HIGH"
    elif len(rows) >= 3:
        breadth_confidence = "MEDIUM"
    else:
        breadth_confidence = "LOW"

    return {
        # Existing downstream fields
        "Sector": sector,
        "Strength": _round(strength),
        "Average Edge": _round(avg_edge),
        "Average Score": _round(avg_score),
        "Average RS": _round(avg_rs),
        "Institutional": _round(institutional),
        "Stocks": len(rows),

        # V1 transparent components
        "Edge Component": _round(edge_component),
        "Score Component": _round(score_component),
        "RS Component": _round(rs_component),
        "Institutional Component": _round(
            institutional_component
        ),
        "Breadth": _round(breadth_component),
        "Breadth Confidence": breadth_confidence,

        "Strength Version": VERSION,
    }


def build_sector_rankings(
    results: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build sector rankings from scanner results.

    This function intentionally does NOT download market data.
    It operates entirely on the existing scanner output.

    Invalid rows and UNKNOWN sectors are excluded.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in results or []:
        if not _valid_row(row):
            continue

        sector = _text(
            row.get("sector", row.get("Sector", ""))
        )

        if not sector:
            continue

        if sector.upper() in {
            "UNKNOWN",
            "N/A",
            "NA",
            "NONE",
        }:
            continue

        groups[sector].append(row)

    rankings = [
        _build_sector_record(
            sector,
            rows,
        )
        for sector, rows in groups.items()
    ]

    rankings.sort(
        key=lambda row: (
            _safe_float(row.get("Strength")),
            _safe_float(row.get("Average RS")),
            _safe_float(row.get("Average Edge")),
            _safe_float(row.get("Average Score")),
            _safe_float(row.get("Stocks")),
        ),
        reverse=True,
    )

    # Stable rank assigned after sorting.
    for rank, row in enumerate(rankings, start=1):
        row["Rank"] = rank

        strength = _safe_float(
            row.get("Strength")
        )

        if strength >= 75:
            rating = "ELITE"
        elif strength >= 65:
            rating = "STRONG"
        elif strength >= 55:
            rating = "POSITIVE"
        elif strength >= 45:
            rating = "NEUTRAL"
        elif strength >= 35:
            rating = "WEAK"
        else:
            rating = "VERY_WEAK"

        row["Rating"] = rating

    return rankings


def get_sector_strength(
    sector: Any,
    sector_rankings: Iterable[Dict[str, Any]],
) -> float:
    """
    Backward-compatible lookup used by main.py.

    Returns 0 when the sector cannot be found.
    """
    target = _text(sector).casefold()

    if not target:
        return 0.0

    for row in sector_rankings or []:
        candidate = _text(
            row.get("Sector", "")
        ).casefold()

        if candidate == target:
            return _safe_float(
                row.get("Strength"),
                0.0,
            )

    return 0.0


def sector_rankings_to_rows(
    sector_rankings: Iterable[Dict[str, Any]],
) -> List[List[Any]]:
    """
    Helper for Google Sheets output.

    Includes the existing columns plus V1 diagnostics.
    """
    headers = [
        "Rank",
        "Sector",
        "Strength",
        "Rating",
        "Average Edge",
        "Average Score",
        "Average RS",
        "Institutional",
        "Breadth",
        "Breadth Confidence",
        "Edge Component",
        "Score Component",
        "RS Component",
        "Institutional Component",
        "Stocks",
        "Strength Version",
    ]

    rows = [headers]

    for row in sector_rankings or []:
        rows.append([
            row.get("Rank", ""),
            row.get("Sector", ""),
            row.get("Strength", ""),
            row.get("Rating", ""),
            row.get("Average Edge", ""),
            row.get("Average Score", ""),
            row.get("Average RS", ""),
            row.get("Institutional", ""),
            row.get("Breadth", ""),
            row.get("Breadth Confidence", ""),
            row.get("Edge Component", ""),
            row.get("Score Component", ""),
            row.get("RS Component", ""),
            row.get("Institutional Component", ""),
            row.get("Stocks", ""),
            row.get("Strength Version", VERSION),
        ])

    return rows


def attach_sector_strength(
    results: Iterable[Dict[str, Any]],
    sector_rankings: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convenience helper.

    Returns the same result dictionaries with sector_strength
    attached. Existing main.py logic can continue using the
    explicit loop instead.
    """
    rankings = list(sector_rankings or [])
    enriched = []

    for row in results or []:
        if not isinstance(row, dict):
            continue

        output = dict(row)

        output["sector_strength"] = get_sector_strength(
            output.get("sector", ""),
            rankings,
        )

        enriched.append(output)

    return enriched


def _self_test() -> None:
    sample = [
        {
            "ticker": "AAA.NS",
            "sector": "Capital Goods",
            "score": 90,
            "edge_rating": 8,
            "rs_score": 60,
            "institutional_rank": 70,
            "trade_action": "STRONG_BUY",
            "signal": "SWING BUY",
        },
        {
            "ticker": "BBB.NS",
            "sector": "Capital Goods",
            "score": 80,
            "edge_rating": 7,
            "rs_score": 50,
            "institutional_rank": 65,
            "trade_action": "BUY",
            "signal": "SWING BUY",
        },
        {
            "ticker": "CCC.NS",
            "sector": "Capital Goods",
            "score": 60,
            "edge_rating": 4,
            "rs_score": 20,
            "institutional_rank": 40,
            "trade_action": "WATCH",
            "signal": "WATCH",
        },
        {
            "ticker": "DDD.NS",
            "sector": "Power",
            "score": 55,
            "edge_rating": 3,
            "rs_score": 15,
            "institutional_rank": 35,
            "trade_action": "IGNORE",
            "signal": "NO TRADE",
        },
    ]

    rankings = build_sector_rankings(sample)

    assert len(rankings) == 2
    assert rankings[0]["Sector"] == "Capital Goods"
    assert 0 <= rankings[0]["Strength"] <= 100
    assert rankings[0]["Stocks"] == 3
    assert rankings[0]["Breadth"] > 0

    strength = get_sector_strength(
        "Capital Goods",
        rankings,
    )

    assert strength == rankings[0]["Strength"]

    rows = sector_rankings_to_rows(rankings)

    assert rows[0][0] == "Rank"
    assert rows[0][1] == "Sector"

    print(
        f"[SELF TEST] {VERSION} PASSED"
    )


if __name__ == "__main__":
    _self_test()
