import pandas as pd

customers = pd.DataFrame(
    {
        "customer_id": ["C-001", "C-002", "C-003", "C-004"],
        "customer_name": ["Asha Rao", "Ben Cole", "Chitra Iyer", "Dev Shah"],
        "email": ["asha@example.com", "ben@example.com", "chitra@example.com", "dev@example.com"],
        "segment": ["Enterprise", "SMB", "Consumer", "SMB"],
        "signup_date": pd.to_datetime(["2022-03-01", "2023-07-15", "2024-01-20", "2024-09-02"]),
    }
)
orders = pd.DataFrame(
    {
        "order_id": [f"O-{i:03d}" for i in range(1, 9)],
        "customer_id": ["C-001", "C-002", "C-001", "C-003", "C-004", "C-002", "C-001", "C-003"],
        "order_date": pd.date_range("2025-01-05", periods=8, freq="10D"),
        "region": ["West", "South", "West", "North", "East", "South", "West", "North"],
        "amount": [1299.0, 459.5, 899.0, 2499.0, 620.0, 310.0, 1750.0, 980.0],
        "units": [2, 5, 1, 3, 4, 2, 6, 1],
    }
)

customers.to_csv("customers.csv", index=False)
orders.to_csv("orders.csv", index=False)
with pd.ExcelWriter("shop.xlsx") as writer:
    orders.to_excel(writer, sheet_name="Orders", index=False)
    customers.to_excel(writer, sheet_name="Customers", index=False)
print("Created customers.csv, orders.csv, shop.xlsx")