from app.models.dataset import Dataset
from app.services.dataset_tables import get_table_profiles

MOSTLY_EMPTY_PCT = 40.0
MAX_ISSUES = 40


def check_quality(dataset: Dataset) -> list[dict]:
    """Problems that tend to make answers wrong, found from the stored profile (no data is re-read)."""
    issues: list[dict] = []

    def add(severity: str, table: str, column: str | None, message: str) -> None:
        issues.append({"severity": severity, "table": table, "column": column, "message": message})

    for t in get_table_profiles(dataset):
        table, rows = t["table"], t["rows"]

        if rows < 20:
            add("info", table, None, f"Only {rows} rows. Averages and trends from so little data may not be reliable.")

        dup = t.get("duplicateRows", 0)
        if dup and rows:
            add(
                "warning",
                table,
                None,
                f"{dup:,} rows ({100 * dup / rows:.1f}%) are exact copies of other rows, so totals and counts may be inflated.",
            )

        for c in t["columns"]:
            name, null_pct = c["name"], c["nullPct"]

            if rows and null_pct >= 100:
                add("warning", table, name, "This column is completely empty.")
            elif null_pct >= MOSTLY_EMPTY_PCT:
                add("warning", table, name, f"{null_pct:g}% of the values are missing, so results using it will be incomplete.")

            if c["distinct"] == 1 and rows > 1 and null_pct < 100:
                add("info", table, name, "Every row has the same value, so it cannot be used to compare anything.")

            if c.get("numericLike"):
                add(
                    "warning",
                    table,
                    name,
                    "Stored as text but looks like numbers (for example with commas or currency symbols), so sums and averages will not work on it.",
                )

    issues.sort(key=lambda i: 0 if i["severity"] == "warning" else 1)
    return issues[:MAX_ISSUES]