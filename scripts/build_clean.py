"""
Builds data/clean/ from data/raw/ by applying the SAME transformations the Power Query
queries in /powerquery do. Use the clean files as a fallback if Power Query gives you
trouble, or to check your own Power Query output row-for-row.

Run:  python build_clean.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

# Dim_Product = products + supplier attributes (snowflake flattened into a star)
suppliers = pd.read_csv(RAW / "suppliers.csv")
products = pd.read_csv(RAW / "products.csv")
dim_product = products.merge(suppliers[["SupplierID", "SupplierName", "SupplierCountry", "StdLeadTimeDays"]],
                             on="SupplierID", how="left")
dim_product.to_csv(CLEAN / "Dim_Product.csv", index=False)

pd.read_csv(RAW / "locations.csv").to_csv(CLEAN / "Dim_Location.csv", index=False)

# Fact_DemandForecast = unpivoted + pivoted forecast, left-joined to actuals
fw = pd.read_csv(RAW / "forecast_plan_wide.csv")
fl = fw.melt(id_vars=["SKU", "LocationID", "ForecastType"], var_name="MonthText", value_name="Units")
fl["Month"] = pd.to_datetime(fl["MonthText"] + "-01")
fc = (fl.pivot_table(index=["SKU", "LocationID", "Month"], columns="ForecastType", values="Units", aggfunc="sum")
        .reset_index().rename(columns={"Statistical": "StatForecastUnits", "Consensus": "ConsensusForecastUnits"}))
fc.columns.name = None
act = pd.read_csv(RAW / "demand_actuals.csv", parse_dates=["Month"])
fdf = fc.merge(act.rename(columns={"DemandUnits": "ActualUnits"}), on=["Month", "SKU", "LocationID"], how="left")
fdf["HasActual"] = fdf["Month"] <= act["Month"].max()
fdf["ActualUnits"] = fdf["ActualUnits"].astype("Int64")
fdf = fdf[["Month", "SKU", "LocationID", "StatForecastUnits", "ConsensusForecastUnits", "ActualUnits", "HasActual"]]
fdf.sort_values(["SKU", "LocationID", "Month"]).to_csv(CLEAN / "Fact_DemandForecast.csv", index=False, date_format="%Y-%m-%d")

pd.read_csv(RAW / "inventory_monthly.csv").to_csv(CLEAN / "Fact_Inventory.csv", index=False)

# Fact_InventoryLots + age buckets
lots = pd.read_csv(RAW / "inventory_lots.csv", parse_dates=["SnapshotDate", "ReceiptDate"])
lots["AgeDays"] = (lots["SnapshotDate"] - lots["ReceiptDate"]).dt.days
bins = [(30, "0-30 days", 1), (60, "31-60 days", 2), (90, "61-90 days", 3), (180, "91-180 days", 4)]


def bucket(d):
    for lim, name, s in bins:
        if d <= lim:
            return name, s
    return "180+ days", 5


lots[["AgeBucket", "AgeBucketSort"]] = lots["AgeDays"].apply(lambda d: pd.Series(bucket(d)))
lots.to_csv(CLEAN / "Fact_InventoryLots.csv", index=False, date_format="%Y-%m-%d")

# Fact_PurchaseOrders: trim/upper SKU, remove duplicates, parse dd-mm-yyyy, derive flags
po = pd.read_csv(RAW / "purchase_orders.csv", dtype=str, keep_default_na=False)
po["SKU"] = po["SKU"].str.strip().str.upper()
po = po.drop_duplicates()
for c in ["PO_Date", "RequestedDate", "ReceiptDate", "SupplierETA"]:
    po[c] = pd.to_datetime(po[c].replace("", None), format="%d-%m-%Y")
po["OrderQty"] = po["OrderQty"].astype(int)
po["ReceivedQty"] = pd.to_numeric(po["ReceivedQty"].replace("", None)).astype("Int64")
rec = po["Status"] == "Received"
po["ExpectedReceiptDate"] = po["ReceiptDate"].where(rec, po["SupplierETA"])
po["OpenQty"] = po["OrderQty"].where(~rec, 0)
po["DelayDays"] = (po["ReceiptDate"] - po["RequestedDate"]).dt.days.where(rec).astype("Int64")
po["OnTimeFlag"] = (po["DelayDays"] <= 3).astype("Int64").where(rec)
po["InFullFlag"] = (po["ReceivedQty"] >= po["OrderQty"]).astype("Int64").where(rec)
po.to_csv(CLEAN / "Fact_PurchaseOrders.csv", index=False, date_format="%Y-%m-%d")

for f in sorted(CLEAN.glob("*.csv")):
    print(f.name, len(pd.read_csv(f)))
