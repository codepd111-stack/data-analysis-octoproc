from app.services.chart_builder import BAR_LIMIT, MAX_SERIES, build_chart
from app.services.query_engine import QueryResult


def result(columns: list[str], rows: list[dict]) -> QueryResult:
    return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=False)


def test_a_single_value_gets_no_chart():
    assert build_chart(result(["total"], [{"total": 5}]), None) is None


def test_no_numeric_column_gets_no_chart():
    rows = [{"a": "x", "b": "y"}, {"a": "z", "b": "w"}]
    assert build_chart(result(["a", "b"], rows), None) is None


def test_bar_chart_from_a_category_and_a_measure():
    rows = [{"region": "North", "total": 175.0}, {"region": "South", "total": 50.5}]
    chart = build_chart(
        result(["region", "total"], rows), {"type": "bar", "x": "region", "y": ["total"]}
    )
    assert chart == {
        "type": "bar",
        "title": "Total by region",
        "xKey": "region",
        "yKeys": ["total"],
        "data": [{"region": "North", "total": 175}, {"region": "South", "total": 50.5}],
    }


def test_temporal_x_defaults_to_a_sorted_line():
    rows = [
        {"month": "2024-02", "total": 95},
        {"month": "2024-01", "total": 150},
        {"month": "2024-03", "total": 10},
    ]
    chart = build_chart(result(["month", "total"], rows), {})
    assert chart["type"] == "line"
    assert [d["month"] for d in chart["data"]] == ["2024-01", "2024-02", "2024-03"]


def test_a_line_needs_three_points():
    rows = [{"month": "2024-01", "total": 1}, {"month": "2024-02", "total": 2}]
    assert build_chart(result(["month", "total"], rows), {"type": "line"})["type"] == "bar"


def test_pie_is_allowed_for_a_small_positive_breakdown():
    rows = [{"k": "a", "v": 5}, {"k": "b", "v": 3}, {"k": "c", "v": 2}]
    assert build_chart(result(["k", "v"], rows), {"type": "pie"})["type"] == "pie"


def test_pie_falls_back_to_bar_for_negative_values():
    rows = [{"k": "a", "v": 5}, {"k": "b", "v": -1}]
    assert build_chart(result(["k", "v"], rows), {"type": "pie"})["type"] == "bar"


def test_second_category_pivots_into_series_keeping_the_top_n():
    rows = [
        {"region": r, "segment": f"seg{s}", "total": s}
        for r in ("N", "S")
        for s in range(MAX_SERIES + 2)
    ]
    chart = build_chart(
        result(["region", "segment", "total"], rows), {"x": "region", "y": ["total"]}
    )
    assert len(chart["yKeys"]) == MAX_SERIES
    assert chart["title"].endswith(f"(top {MAX_SERIES} of {MAX_SERIES + 2})")
    assert set(chart["data"][0]) == {"region", *chart["yKeys"]}
    assert [d["region"] for d in chart["data"]] == ["N", "S"]


def test_bars_are_capped():
    rows = [{"k": f"k{i}", "v": i} for i in range(BAR_LIMIT + 5)]
    chart = build_chart(result(["k", "v"], rows), {"type": "bar"})
    assert len(chart["data"]) == BAR_LIMIT
    assert f"(first {BAR_LIMIT})" in chart["title"]


def test_unusable_hints_are_ignored():
    rows = [{"region": "N", "total": 1}, {"region": "S", "total": 2}]
    chart = build_chart(
        result(["region", "total"], rows), {"type": "scatter", "x": "nope", "y": "missing"}
    )
    assert chart["type"] == "bar"
    assert chart["xKey"] == "region"
    assert chart["yKeys"] == ["total"]


def test_labels_and_numbers_are_cleaned():
    rows = [
        {"flag": True, "v": 1.23456},
        {"flag": None, "v": float("nan")},
        {"flag": False, "v": 1000.0},
    ]
    chart = build_chart(result(["flag", "v"], rows), {"type": "bar"})
    assert [d["flag"] for d in chart["data"]] == ["Yes", "(blank)", "No"]
    assert [d["v"] for d in chart["data"]] == [1.23, 0, 1000]
