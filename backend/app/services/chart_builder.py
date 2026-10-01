import math

from app.services.query_engine import QueryResult

MAX_SERIES = 6
MAX_Y = 3
BAR_LIMIT = 30
PIE_LIMIT = 8

TEMPORAL_WORDS = {"date", "day", "week", "month", "quarter", "year", "period", "time", "timestamp"}


def _is_numeric_column(rows: list[dict], col: str) -> bool:
    seen = False
    for r in rows:
        v = r.get(col)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        seen = True
    return seen


def _num(v: object) -> int | float:
    if v is None or isinstance(v, str):
        return 0
    if isinstance(v, bool):
        return int(v)
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if math.isnan(f) or math.isinf(f):
        return 0
    r = round(f, 4) if abs(f) < 1 else round(f, 2)
    return int(r) if r == int(r) else r


def _label(v: object) -> str:
    if v is None:
        return "(blank)"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return s[:40] if s else "(blank)"


def _looks_temporal(x: str, rows: list[dict]) -> bool:
    if set(x.lower().split("_")) & TEMPORAL_WORDS:
        return True
    sample = [r.get(x) for r in rows if r.get(x) is not None][:5]
    return bool(sample) and all(
        isinstance(v, str) and len(v) >= 7 and v[:4].isdigit() and v[4] == "-" for v in sample
    )


def _pivot(rows: list[dict], x: str, series_col: str, value_col: str):
    """Long format (x, series, value) -> wide format with one key per series."""
    totals: dict[str, float] = {}
    for r in rows:
        s = _label(r.get(series_col))
        totals[s] = totals.get(s, 0.0) + abs(float(_num(r.get(value_col))))
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top = [s for s, _ in ranked[:MAX_SERIES]]

    by_x: dict[str, dict[str, float]] = {}
    order: list[str] = []
    for r in rows:
        xv, sv = _label(r.get(x)), _label(r.get(series_col))
        if sv not in top:
            continue
        if xv not in by_x:
            by_x[xv] = {}
            order.append(xv)
        by_x[xv][sv] = by_x[xv].get(sv, 0) + _num(r.get(value_col))

    data = [{x: xv, **{s: _num(by_x[xv].get(s, 0)) for s in top}} for xv in order]
    return data, top, len(totals)


def build_chart(result: QueryResult, hint: object) -> dict | None:
    """Returns a ChartSpec dict (camelCase keys) or None when a chart would not help."""
    rows = result.rows
    if len(rows) < 2:
        return None  # a single value is better explained in words

    hint = hint if isinstance(hint, dict) else {}
    columns = result.columns
    numeric = [c for c in columns if _is_numeric_column(rows, c)]
    if not numeric:
        return None
    cats = [c for c in columns if c not in numeric]

    x = hint.get("x") if hint.get("x") in columns else None
    if x is None:
        x = cats[0] if cats else columns[0]

    raw_y = hint.get("y")
    if isinstance(raw_y, str):
        raw_y = [raw_y]
    ys = [y for y in (raw_y if isinstance(raw_y, list) else []) if y in numeric and y != x]
    if not ys:
        ys = [c for c in numeric if c != x]
    ys = list(dict.fromkeys(ys))[:MAX_Y]
    if not ys:
        return None

    series_cols = [c for c in cats if c != x]
    pivoted = False
    suffix = ""
    if len(ys) == 1 and series_cols:
        data, y_keys, total_series = _pivot(rows, x, series_cols[0], ys[0])
        pivoted = True
        if total_series > MAX_SERIES:
            suffix = f" (top {MAX_SERIES} of {total_series})"
    else:
        data = [{x: _label(r.get(x)), **{y: _num(r.get(y)) for y in ys}} for r in rows]
        y_keys = ys
    if not data or not y_keys:
        return None

    temporal = _looks_temporal(x, rows)
    ctype = hint.get("type") if hint.get("type") in ("bar", "line", "pie") else None
    if ctype is None:
        ctype = "line" if temporal else "bar"

    if ctype == "pie":
        values = [d[y_keys[0]] for d in data]
        if (
            pivoted
            or len(y_keys) != 1
            or not 2 <= len(data) <= PIE_LIMIT
            or any(v < 0 for v in values)
            or sum(values) <= 0
        ):
            ctype = "bar"
    if ctype == "line" and len(data) < 3:
        ctype = "bar"

    if ctype == "line" and temporal:
        data.sort(key=lambda d: str(d[x]))
    if ctype in ("bar", "pie") and len(data) > BAR_LIMIT:
        data = data[:BAR_LIMIT]
        suffix += f" (first {BAR_LIMIT})"

    title = str(hint.get("title") or "").strip()[:80]
    if not title:
        title = f"{ys[0].replace('_', ' ').capitalize()} by {x.replace('_', ' ')}"

    return {"type": ctype, "title": title + suffix, "xKey": x, "yKeys": y_keys, "data": data}