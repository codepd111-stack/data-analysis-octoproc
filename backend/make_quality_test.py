import pandas as pd

rows = []
for i in range(1, 31):
    rows.append(
        {
            "order_id": f"O-{i:03d}",
            "amount": f"₹{1000 + i * 37:,}.00",
            "region": ["West", "South", "North"][i % 3],
            "status": "shipped",
            "notes": "gift" if i % 5 == 0 else None,
        }
    )
df = pd.DataFrame(rows)
df = pd.concat([df, df.iloc[:3]])  # 3 duplicate rows
df.to_csv("messy.csv", index=False, encoding="utf-8")
print("Created messy.csv")