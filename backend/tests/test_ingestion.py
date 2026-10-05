from datetime import timedelta

import pandas as pd

from app.core.utils import utcnow
from app.models.dataset import Dataset
from app.services.ingestion import (
    INTERRUPTED_ERROR,
    clean_columns,
    coerce_dates,
    fail_interrupted_datasets,
    load_tables,
    make_table_name,
    prepare_dataframe,
    unique_table_name,
)

# ---------- dataframe preparation ----------


def test_clean_columns_snake_cases_and_dedupes():
    df = pd.DataFrame(columns=["Order ID", "order id", "2024 Sales", "", "Total (USD)"])
    assert list(clean_columns(df).columns) == [
        "order_id",
        "order_id_2",
        "c_2024_sales",
        "col_3",
        "total_usd",
    ]


def test_coerce_dates_only_touches_date_hinted_columns():
    df = pd.DataFrame(
        {
            "order_date": ["2024-01-05", "2024-02-01", None],
            "code": ["2024-01-05", "2024-02-01", "2024-03-01"],
        }
    )
    out = coerce_dates(df)
    assert pd.api.types.is_datetime64_any_dtype(out["order_date"])
    assert not pd.api.types.is_datetime64_any_dtype(out["code"])


def test_coerce_dates_leaves_mostly_unparseable_columns_alone():
    df = pd.DataFrame({"created_at": ["2024-01-05", "soon", "later", "never"]})
    assert not pd.api.types.is_datetime64_any_dtype(coerce_dates(df)["created_at"])


def test_prepare_dataframe_makes_mixed_object_columns_plain_strings():
    df = pd.DataFrame({"Mixed": pd.Series([1, "two", None, 3.5], dtype=object)})
    out = prepare_dataframe(df)
    assert list(out.columns) == ["mixed"]
    values = out["mixed"].tolist()
    assert values[:2] == ["1", "two"]
    assert pd.isna(values[2])  # stays null (Parquet writes it as such)
    assert values[3] == "3.5"


def test_table_names_are_sql_friendly():
    assert make_table_name("Sales Q1 (final)") == "sales_q1_final"
    assert make_table_name("2024 data") == "t_2024_data"
    assert make_table_name("!!!") == "data"


def test_unique_table_name_appends_a_counter():
    used: set[str] = set()
    assert unique_table_name("orders", used) == "orders"
    assert unique_table_name("Orders", used) == "orders_2"
    assert unique_table_name("orders", used) == "orders_3"


def test_load_tables_reads_csv_and_every_non_empty_excel_sheet(tmp_path):
    csv = tmp_path / "orders.csv"
    csv.write_text("a,b\n1,2\n")
    [(label, df)] = load_tables(csv)
    assert label == "orders"
    assert df.shape == (1, 2)

    xlsx = tmp_path / "shop.xlsx"
    with pd.ExcelWriter(xlsx) as writer:
        pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="items", index=False)
        pd.DataFrame({"y": [2]}).to_excel(writer, sheet_name="stores", index=False)
        pd.DataFrame().to_excel(writer, sheet_name="empty", index=False)
    assert [label for label, _ in load_tables(xlsx)] == ["shop_items", "shop_stores"]


# ---------- interrupted jobs ----------


def _dataset(db, status: str = "processing", age: timedelta | None = None) -> Dataset:
    ds = Dataset(
        name="n", file_name="f.csv", raw_key="raw/x/f.csv", status=status, progress=50, stage="Reading"
    )
    db.add(ds)
    db.commit()
    if age is not None:
        ds.updated_at = utcnow() - age  # an explicit value wins over the onupdate default
        db.commit()
    return ds


def test_startup_sweep_fails_every_processing_dataset(db):
    stuck = _dataset(db)
    done = _dataset(db, status="approved")
    assert fail_interrupted_datasets(db) >= 1
    db.refresh(stuck)
    db.refresh(done)
    assert (stuck.status, stuck.stage, stuck.error) == ("failed", None, INTERRUPTED_ERROR)
    assert done.status == "approved"


def test_running_sweep_only_fails_stale_datasets(db):
    fresh = _dataset(db)
    stale = _dataset(db, age=timedelta(hours=1))
    fail_interrupted_datasets(db, older_than=timedelta(minutes=15))
    db.refresh(fresh)
    db.refresh(stale)
    assert fresh.status == "processing"
    assert stale.status == "failed"
