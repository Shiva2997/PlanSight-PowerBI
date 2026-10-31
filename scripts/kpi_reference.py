"""
Independent pandas implementation of the dashboard KPIs (same definitions as dax/measures.dax).
Use it to validate your DAX: the numbers printed here are the "checkpoint values" in BUILD_GUIDE.md.

Run:  python kpi_reference.py            (prints checkpoints)
      python kpi_reference.py --json out.json   (also writes the series used for the mockups)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

C = Path(__file__).resolve().parents[1] / "data" / "clean"
AS_OF = pd.Timestamp("2026-10-31")
FY26 = (pd.Timestamp("2025-11-01"), pd.Timestamp("2026-10-31"))
FY25 = (pd.Timestamp("2024-11-01"), pd.Timestamp("2025-10-31"))

prod = pd.read_csv(C / "Dim_Product.csv")
loc = pd.read_csv(C / "Dim_Location.csv")
fdf = pd.read_csv(C / "Fact_DemandForecast.csv", parse_dates=["Month"]).merge(prod, on="SKU")
inv = pd.read_csv(C / "Fact_Inventory.csv", parse_dates=["SnapshotDate"]).merge(prod, on="SKU").merge(loc, on="LocationID")
lots = pd.read_csv(C / "Fact_InventoryLots.csv", parse_dates=["SnapshotDate", "ReceiptDate"]).merge(prod, on="SKU")
po = pd.read_csv(C / "Fact_PurchaseOrders.csv", parse_dates=["PO_Date", "RequestedDate", "ReceiptDate", "SupplierETA", "ExpectedReceiptDate"]).merge(
    prod[["SKU", "SupplierName", "Category"]], on="SKU")


def between(df, col, rng):
    return df[(df[col] >= rng[0]) & (df[col] <= rng[1])]


# ---------------- forecast accuracy ----------------
def acc(df):
    h = df[df.HasActual]
    a = h.ActualUnits.sum()
    fa = max(0, 1 - (h.ConsensusForecastUnits - h.ActualUnits).abs().sum() / a)
    fs = max(0, 1 - (h.StatForecastUnits - h.ActualUnits).abs().sum() / a)
    return dict(actual=a, fa=fa, fa_stat=fs, fva=fa - fs,
                bias=h.ConsensusForecastUnits.sum() / a - 1, bias_stat=h.StatForecastUnits.sum() / a - 1)


def fill(df):
    return df.ShippedUnits.sum() / (df.ShippedUnits.sum() + df.UnfilledUnits.sum())


# ---------------- stock status at a month-end ----------------
def stock_table(snap):
    oh = inv[inv.SnapshotDate == snap][["SKU", "LocationID", "ClosingUnits", "UnitCostINR", "Category", "ProductName", "DCName"]]
    f3 = fdf[(fdf.Month > snap) & (fdf.Month <= snap + pd.offsets.MonthEnd(3))].groupby(["SKU", "LocationID"]).ConsensusForecastUnits.sum().rename("F3")
    t = oh.merge(f3, on=["SKU", "LocationID"], how="left").fillna({"F3": 0})
    t["WOS"] = np.where(t.F3 > 0, t.ClosingUnits / (t.F3 / 13), np.nan)

    def status(r):
        if r.ClosingUnits <= 0 and r.F3 > 0:
            return "Stocked out"
        if r.ClosingUnits <= 0:
            return None
        if r.F3 <= 0:
            return "Excess"
        if r.WOS < 1.5:
            return "Stockout risk"
        if r.WOS <= 8:
            return "Healthy"
        if r.WOS <= 12:
            return "Watch"
        return "Excess"

    t["Status"] = t.apply(status, axis=1)
    t["ExcessINR"] = np.maximum(0, t.ClosingUnits - 12 * t.F3 / 13) * t.UnitCostINR
    return t


def projection():
    oh = inv[inv.SnapshotDate == AS_OF].set_index(["SKU", "LocationID"]).ClosingUnits
    cols = {}
    for me in pd.date_range("2026-11-30", "2027-01-31", freq="ME"):
        sup = po[(po.ExpectedReceiptDate > AS_OF) & (po.ExpectedReceiptDate <= me)].groupby(["SKU", "LocationID"]).OpenQty.sum()
        dem = fdf[(fdf.Month > AS_OF) & (fdf.Month <= me)].groupby(["SKU", "LocationID"]).ConsensusForecastUnits.sum()
        cols[me.strftime("%b-%y")] = oh.add(sup, fill_value=0).sub(dem, fill_value=0)
    return pd.DataFrame(cols)


def main():
    out = {}
    d26, d25 = between(fdf, "Month", FY26), between(fdf, "Month", FY25)
    i26 = between(inv, "SnapshotDate", FY26)
    a26 = acc(d26)
    rec26 = between(po[po.Status == "Received"], "RequestedDate", FY26)
    st = stock_table(AS_OF)
    lo = lots[lots.SnapshotDate == AS_OF].assign(V=lambda x: x.UnitsOnHand * x.UnitCostINR)
    pj = projection()
    short = pj[(pj < 0).any(axis=1)]

    cp = [
        ("Actual Units (FY26)", f"{d26.ActualUnits.sum():,.0f}"),
        ("Demand Value (₹ Cr, FY26)", f"{(d26.ActualUnits * d26.ListPriceINR).sum() / 1e7:,.1f}"),
        ("Demand Growth YoY % (FY26 vs FY25)", f"{d26.ActualUnits.sum() / d25.ActualUnits.sum() - 1:.1%}"),
        ("Forecast Accuracy % (FY26)", f"{a26['fa']:.1%}"),
        ("Stat Forecast Accuracy % (FY26)", f"{a26['fa_stat']:.1%}"),
        ("Forecast Value Add (FY26)", f"{a26['fva'] * 100:+.1f} pts"),
        ("Forecast Bias % (FY26)", f"{a26['bias']:+.1%}"),
        ("Fill Rate % (FY26)", f"{fill(i26):.1%}"),
        ("Stockout Events (FY26)", f"{(i26.UnfilledUnits > 0).sum():,}"),
        ("Lost Sales Value (₹ Cr, FY26)", f"{(i26.UnfilledUnits * i26.ListPriceINR).sum() / 1e7:,.1f}"),
        ("Inventory Value (₹ Cr, Oct-26)", f"{(st.ClosingUnits * st.UnitCostINR).sum() / 1e7:,.1f}"),
        ("Weeks of Supply (Oct-26)", f"{st.ClosingUnits.sum() / (st.F3.sum() / 13):.1f}"),
        ("Excess Value (₹ Cr, Oct-26)", f"{st.ExcessINR.sum() / 1e7:,.1f}"),
        ("Aged >90d Value (₹ Cr, Oct-26)", f"{lo[lo.AgeDays > 90].V.sum() / 1e7:,.1f}"),
        ("Aged >90d % (Oct-26)", f"{lo[lo.AgeDays > 90].V.sum() / lo.V.sum():.1%}"),
        ("On-Time Delivery % (FY26)", f"{rec26.OnTimeFlag.mean():.1%}"),
        ("OTIF % (FY26)", f"{((rec26.OnTimeFlag == 1) & (rec26.InFullFlag == 1)).mean():.1%}"),
        ("Avg Delay Days, late lines (FY26)", f"{rec26[rec26.OnTimeFlag == 0].DelayDays.mean():.1f}"),
        ("Past-Due Open PO Lines", f"{((po.Status == 'Open') & (po.RequestedDate <= AS_OF)).sum()}"),
        ("Shortage Risk SKU-DCs (Nov-26 to Jan-27)", f"{len(short)}"),
        ("Projected Shortage Units (Nov-26 to Jan-27)", f"{(-pj.min(axis=1)).clip(lower=0).sum():,.0f}"),
    ]
    print("\nCHECKPOINT VALUES")
    for k, v in cp:
        print(f"  {k:<46} {v}")

    print("\nSKU-DC count by status (Oct-26):", st.Status.value_counts().to_dict())

    cat = pd.DataFrame({c: acc(g) for c, g in d26.groupby("Category")}).T
    cat["fill"] = i26.groupby("Category").apply(fill, include_groups=False)
    print("\nBy category (FY26):\n", cat[["fa", "fa_stat", "fva", "bias", "fill"]].round(3).to_string())
    print("\nFill rate by DC (FY26):\n", i26.groupby("DCName").apply(fill, include_groups=False).round(3).to_string())
    print("\nOTD by supplier (FY26):\n", rec26.groupby("SupplierName").OnTimeFlag.mean().round(3).to_string())
    s1 = po[(po.Status == "Received") & (po.SupplierID == "SUP01")]
    print("\nODM China OTD by requested month:\n", s1.groupby(s1.RequestedDate.dt.strftime("%Y-%m")).OnTimeFlag.mean().tail(8).round(2).to_string())
    cn = inv[inv.Category == "Consumer Notebooks"]
    print("\nConsumer notebook fill rate by month:\n", cn.groupby(cn.SnapshotDate.dt.strftime("%Y-%m")).apply(fill, include_groups=False).tail(6).round(3).to_string())
    print("\nTop excess (₹ Cr):\n", (st.groupby("ProductName").ExcessINR.sum().sort_values(ascending=False).head(5) / 1e7).round(1).to_string())
    print("\nAged >90d by product (₹ Cr):\n", (lo[lo.AgeDays > 90].groupby("ProductName").V.sum().sort_values(ascending=False).head(5) / 1e7).round(1).to_string())
    print("\nProjected shortages:\n", short.round(0).to_string())
    reb = st.groupby("SKU").apply(lambda g: pd.Series({
        "excess_dcs": (g.Status == "Excess").sum(),
        "short_dcs": g.Status.isin(["Stocked out", "Stockout risk"]).sum()}), include_groups=False)
    reb = reb[(reb.excess_dcs > 0) & (reb.short_dcs > 0)]
    print("\nRebalance opportunities:\n", reb.to_string())
    fest = d26[d26.Month.dt.month.isin([9, 10, 11]) & (d26.Category == "Consumer Notebooks") & (d26.LifecycleStatus.isin(["Mature", "Growth"]))]
    print("\nMature consumer NB, festive months FY26:", {k: round(v, 3) for k, v in acc(fest).items() if k != "actual"})

    # series for mockups
    months = sorted(fdf.Month.unique())
    m_lab = [pd.Timestamp(m).strftime("%b-%y") for m in months]
    g = fdf.groupby("Month")
    out["months"] = m_lab
    out["actual"] = [None if not h else int(v) for v, h in zip(g.ActualUnits.sum(), g.HasActual.all())]
    out["consensus"] = [int(v) for v in g.ConsensusForecastUnits.sum()]
    out["stat"] = [int(v) for v in g.StatForecastUnits.sum()]
    hist = fdf[fdf.HasActual]
    out["hist_months"] = [pd.Timestamp(m).strftime("%b-%y") for m in sorted(hist.Month.unique())]
    out["fa_month"] = [acc(gr)["fa"] for _, gr in hist.groupby("Month")]
    out["fa_stat_month"] = [acc(gr)["fa_stat"] for _, gr in hist.groupby("Month")]
    out["fill_month"] = [fill(gr) for _, gr in inv.groupby("SnapshotDate")]
    out["unfilled_month"] = [int(v) for v in inv.groupby("SnapshotDate").UnfilledUnits.sum()]
    out["inv_value_month"] = [float(v) / 1e7 for v in (inv.ClosingUnits * inv.UnitCostINR).groupby(inv.SnapshotDate).sum()]
    out["cat"] = cat.reset_index().rename(columns={"index": "Category"}).to_dict(orient="list")
    out["status_counts"] = st.Status.value_counts().to_dict()
    out["status_matrix"] = st.pivot_table(index="SKU", columns="LocationID", values="Status", aggfunc="first").fillna("").to_dict()
    out["wos_matrix"] = st.pivot_table(index="SKU", columns="LocationID", values="WOS", aggfunc="first").round(1).fillna(-1).to_dict()
    lo["Bucket"] = lo.AgeBucket
    out["aging"] = (lo.groupby(["Category", "AgeBucket"]).V.sum() / 1e7).unstack(fill_value=0).to_dict()
    out["inv_by_cat"] = (st.assign(V=st.ClosingUnits * st.UnitCostINR).groupby("Category").V.sum() / 1e7).to_dict()
    rec = po[po.Status == "Received"].copy()
    rec["M"] = rec.RequestedDate.dt.strftime("%b-%y")
    rec["Mo"] = rec.RequestedDate.dt.to_period("M")
    rec = between(rec, "RequestedDate", FY26)
    otd = rec.groupby(["Mo", "SupplierName"]).OnTimeFlag.mean().unstack()
    out["otd_months"] = [p.strftime("%b-%y") for p in otd.index]
    out["otd"] = {k: [None if pd.isna(x) else float(x) for x in v] for k, v in otd.to_dict(orient="list").items()}
    out["delay_by_sup"] = rec[rec.OnTimeFlag == 0].groupby("SupplierName").DelayDays.mean().to_dict()
    out["otd_by_sup"] = rec.groupby("SupplierName").OnTimeFlag.mean().to_dict()
    out["shortages"] = short.reset_index().merge(prod[["SKU", "ProductName"]], on="SKU").merge(loc[["LocationID", "DCName"]], on="LocationID").to_dict(orient="records")
    out["checkpoints"] = cp
    out["fill_by_dc"] = i26.groupby("DCName").apply(fill, include_groups=False).to_dict()
    out["excess_top"] = (st.groupby("ProductName").ExcessINR.sum().sort_values(ascending=False).head(6) / 1e7).to_dict()
    open_po = po[po.Status != "Received"].sort_values("ExpectedReceiptDate")
    out["past_due"] = open_po[(open_po.Status == "Open") & (open_po.RequestedDate <= AS_OF)].head(8)[
        ["PO_Line_ID", "SKU", "LocationID", "SupplierName", "OpenQty", "RequestedDate", "ExpectedReceiptDate"]].astype(str).to_dict(orient="records")
    out["reb"] = reb.reset_index().to_dict(orient="records")

    if "--json" in sys.argv:
        path = sys.argv[sys.argv.index("--json") + 1]
        Path(path).write_text(json.dumps(out, default=float, indent=1))


if __name__ == "__main__":
    main()
