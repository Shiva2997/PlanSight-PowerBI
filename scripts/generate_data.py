"""
PlanSight - synthetic supply chain planning dataset generator
=============================================================

Simulates 24 months (FY25-FY26, fiscal year Nov-Oct) of monthly supply chain
planning data for a PC & printing business in India:

  * 37 SKUs across notebooks, desktops, monitors, printers, supplies, accessories
  * 8 distribution centres (DCs) across India
  * 5 suppliers with different lead times and delivery reliability
  * customer demand, statistical + consensus forecasts (lag 1)
  * an order-up-to replenishment policy that places purchase orders
  * FIFO inventory lots (for ageing), stockouts and fill rate
  * open + planned purchase orders and a 3-month forward forecast

Business events built into the data (so the dashboard has real stories to find):
  1. Festive-season optimism: sales inflates consumer notebook forecasts in Sep-Nov.
  2. Commercial deals: sales knows most B2B deals in advance, so consensus beats stat.
  3. NPI launches (Gaming 15, Premium Business 13, Consumer 14 Core 5).
  4. End-of-life: Consumer Notebook 14 (Core i3) demand falls from May 2026 but the
     forecast is cut late, creating excess and aged stock.
  5. Declining inkjet all-in-ones & cartridges vs. fast-growing ink-tank printers & ink.
  6. Regional shift: Hyderabad demand grows fast from Jan 2026, Kolkata declines.
  7. Supplier disruption: the China ODM delivers 3-7 weeks late for late-Jul to Oct 2026 due dates.

All data is synthetic. Run:  python generate_data.py
"""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
rng = np.random.default_rng(SEED)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------------------
# Calendar: t = 0 is Nov 2023 (12-month burn-in, not exported). Exported history is
# t = 12 (Nov 2024) .. t = 35 (Oct 2026). t = 36..38 (Nov 2026 - Jan 2027) is the future.
# --------------------------------------------------------------------------------------
MONTHS = pd.date_range("2023-11-01", "2027-04-01", freq="MS")  # extra months = planning horizon
T_OUT, T_LAST, T_END = 12, 35, 38
T_SIM = T_END + 3
AS_OF = pd.Timestamp("2026-10-31")


def month_end(t: int) -> pd.Timestamp:
    return MONTHS[t] + pd.offsets.MonthEnd(0)


def t_of(date: pd.Timestamp) -> int:
    return (date.year - 2023) * 12 + date.month - 11


# --------------------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------------------
SUPPLIERS = pd.DataFrame(
    [
        # id, name, country, lead days, ship mode, planning lead months, delay mean, delay sd
        ("SUP01", "ODM Partner - China", "China", 60, "Ocean", 2, -2.0, 5.0),
        ("SUP02", "Contract Manufacturer - India", "India", 30, "Road", 1, -3.0, 4.0),
        ("SUP03", "Imaging Plant - Malaysia", "Malaysia", 45, "Ocean", 1, -1.0, 5.0),
        ("SUP04", "Supplies Plant - Singapore", "Singapore", 32, "Ocean", 1, -3.0, 3.0),
        ("SUP05", "Peripherals Partner - Taiwan", "Taiwan", 42, "Ocean", 1, 0.0, 5.0),
    ],
    columns=["SupplierID", "SupplierName", "SupplierCountry", "StdLeadTimeDays", "ShipMode",
             "x_lt_months", "x_delay_mu", "x_delay_sd"],
)
SUP = SUPPLIERS.set_index("SupplierID")

LOCATIONS = pd.DataFrame(
    [
        ("DC01", "Gurugram DC", "Gurugram", "Haryana", "North", "Metro", 28.4595, 77.0266, 0.20),
        ("DC02", "Bhiwandi DC", "Bhiwandi (Mumbai)", "Maharashtra", "West", "Metro", 19.2813, 73.0483, 0.19),
        ("DC03", "Bengaluru DC", "Bengaluru", "Karnataka", "South", "Metro", 12.9716, 77.5946, 0.15),
        ("DC04", "Chennai DC", "Chennai", "Tamil Nadu", "South", "Metro", 13.0827, 80.2707, 0.11),
        ("DC05", "Hyderabad DC", "Hyderabad", "Telangana", "South", "Metro", 17.3850, 78.4867, 0.10),
        ("DC06", "Kolkata DC", "Kolkata", "West Bengal", "East", "Regional", 22.5726, 88.3639, 0.10),
        ("DC07", "Ahmedabad DC", "Ahmedabad", "Gujarat", "West", "Regional", 23.0225, 72.5714, 0.08),
        ("DC08", "Lucknow DC", "Lucknow", "Uttar Pradesh", "North", "Regional", 26.8467, 80.9462, 0.07),
    ],
    columns=["LocationID", "DCName", "City", "State", "Region", "DCType", "Latitude", "Longitude", "x_share"],
)
METRO = LOCATIONS.loc[LOCATIONS.DCType == "Metro", "LocationID"].tolist()

# season profiles by calendar month (1..12)
SEASON = {
    "consumer": {1: .90, 2: .80, 3: .85, 4: .85, 5: .95, 6: 1.15, 7: 1.20, 8: 1.00, 9: 1.10, 10: 1.45, 11: 1.00, 12: .95},
    "commercial": {1: .95, 2: 1.00, 3: 1.35, 4: .80, 5: .90, 6: 1.05, 7: .95, 8: .95, 9: 1.05, 10: .95, 11: .95, 12: 1.10},
    "supplies": {1: 1.0, 2: .97, 3: 1.05, 4: .98, 5: 1.0, 6: 1.08, 7: 1.10, 8: 1.02, 9: .98, 10: .92, 11: .95, 12: .95},
}
SEASON["mixed"] = {m: (SEASON["consumer"][m] + SEASON["commercial"][m]) / 2 for m in range(1, 13)}
for prof in SEASON.values():  # normalise to mean 1
    s = sum(prof.values()) / 12
    for m in prof:
        prof[m] /= s

T_MAY26, T_MAR26, T_JUN25 = t_of(pd.Timestamp("2026-05-01")), t_of(pd.Timestamp("2026-03-01")), t_of(pd.Timestamp("2025-06-01"))

# sku, name, category, segment, season, supplier, base units/month (national, Nov-24 level),
# yoy growth, cv, case pack, unit cost, list price, launch t, eol t, metro only, planner bias tag
P = [
    ("NB-C14-I3", "Consumer Notebook 14 (Core i3)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 5200, 0.00, .22, 10, 32000, 41000, None, T_MAY26, False, "festive"),
    ("NB-C14-C5", "Consumer Notebook 14 (Core 5, 2026)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 5400, 0.00, .22, 10, 36000, 46000, T_MAY26, None, False, "festive"),
    ("NB-C15-I5", "Consumer Notebook 15 (Core i5)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 4200, 0.06, .22, 10, 42000, 54000, None, None, False, "festive"),
    ("NB-C15-R5", "Consumer Notebook 15 (Ryzen 5)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 3000, 0.10, .22, 10, 39000, 50000, None, None, False, "festive"),
    ("NB-C14-I7", "Consumer Notebook 14 (Core i7)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 1500, 0.04, .25, 10, 58000, 74000, None, None, False, "festive"),
    ("NB-CNV-14", "2-in-1 Convertible 14", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 900, 0.03, .28, 10, 62000, 79000, None, None, False, "festive"),
    ("NB-GAM-15", "Gaming Notebook 15 (RTX 4050)", "Consumer Notebooks", "Consumer", "consumer", "SUP01", 1100, 0.00, .30, 10, 68000, 87000, T_JUN25, None, False, "festive"),
    ("NB-B14-I5", "Business Notebook 14 (Core i5)", "Commercial Notebooks", "Commercial", "commercial", "SUP02", 3800, 0.08, .25, 10, 52000, 66000, None, None, False, "deals"),
    ("NB-B14-I7", "Business Notebook 14 (Core i7)", "Commercial Notebooks", "Commercial", "commercial", "SUP02", 1800, 0.08, .25, 10, 68000, 86000, None, None, False, "deals"),
    ("NB-B15-I5", "Business Notebook 15 (Core i5)", "Commercial Notebooks", "Commercial", "commercial", "SUP02", 1600, 0.02, .25, 10, 50000, 63000, None, None, False, "deals"),
    ("NB-PRM-13", "Premium Business 13 (Core Ultra 7)", "Commercial Notebooks", "Commercial", "commercial", "SUP01", 700, 0.00, .30, 10, 98000, 125000, T_MAR26, None, False, "deals"),
    ("NB-WKS-16", "Mobile Workstation 16", "Commercial Notebooks", "Commercial", "commercial", "SUP01", 220, 0.05, .45, 5, 140000, 178000, None, None, True, "deals"),
    ("DT-B-MINI", "Business Mini Desktop (Core i5)", "Desktops", "Commercial", "commercial", "SUP02", 1400, 0.05, .25, 10, 38000, 48000, None, None, False, "deals"),
    ("DT-B-TWR", "Business Tower Desktop (Core i5)", "Desktops", "Commercial", "commercial", "SUP02", 1900, -0.04, .25, 10, 36000, 45000, None, None, False, "deals"),
    ("DT-AIO-24", "All-in-One 24 (Core i5)", "Desktops", "Consumer", "mixed", "SUP02", 1200, 0.03, .25, 10, 52000, 66000, None, None, False, "none"),
    ("DT-C-TWR", "Consumer Tower Desktop (Core i3)", "Desktops", "Consumer", "consumer", "SUP02", 800, -0.08, .28, 10, 30000, 38000, None, None, False, "festive"),
    ("MN-22-FHD", "Monitor 22 FHD", "Monitors", "Consumer", "mixed", "SUP05", 3500, 0.00, .25, 20, 6500, 8500, None, None, False, "none"),
    ("MN-24-FHD", "Monitor 24 FHD", "Monitors", "Commercial", "mixed", "SUP05", 4200, 0.06, .25, 20, 8200, 10800, None, None, False, "none"),
    ("MN-27-QHD", "Monitor 27 QHD", "Monitors", "Consumer", "mixed", "SUP05", 1400, 0.12, .28, 20, 17500, 23000, None, None, False, "none"),
    ("MN-24-USBC", "Monitor 24 USB-C", "Monitors", "Commercial", "mixed", "SUP05", 900, 0.15, .30, 20, 15500, 20000, None, None, False, "none"),
    ("PR-IT-HOME", "Ink Tank Printer (Home)", "Printers", "Consumer", "consumer", "SUP03", 7000, 0.20, .22, 10, 9800, 12900, None, None, False, "conservative"),
    ("PR-IT-WL", "Ink Tank Printer (Wireless)", "Printers", "Consumer", "consumer", "SUP03", 4200, 0.24, .22, 10, 13500, 17500, None, None, False, "conservative"),
    ("PR-IJ-AIO", "Inkjet All-in-One (Home)", "Printers", "Consumer", "consumer", "SUP03", 3800, -0.30, .25, 10, 5200, 6900, None, None, False, "hopeful"),
    ("PR-LJ-MONO", "Mono Laser Printer (SMB)", "Printers", "Commercial", "commercial", "SUP03", 2600, 0.03, .25, 10, 11500, 15000, None, None, False, "deals"),
    ("PR-LJ-MFP", "Mono Laser MFP (SMB)", "Printers", "Commercial", "commercial", "SUP03", 1800, 0.06, .25, 10, 19500, 25500, None, None, False, "deals"),
    ("PR-CLJ-MFP", "Color Laser MFP (Office)", "Printers", "Commercial", "commercial", "SUP03", 260, 0.04, .45, 5, 52000, 68000, None, None, True, "deals"),
    ("SP-INK-BLK", "Ink Bottle - Black", "Supplies", "Consumer", "supplies", "SUP04", 52000, 0.22, .12, 100, 420, 650, None, None, False, "conservative"),
    ("SP-INK-CLR", "Ink Bottle - Color 3-pack", "Supplies", "Consumer", "supplies", "SUP04", 30000, 0.22, .12, 100, 980, 1450, None, None, False, "conservative"),
    ("SP-IJ-BLK", "Inkjet Cartridge - Black", "Supplies", "Consumer", "supplies", "SUP04", 36000, -0.15, .12, 100, 680, 999, None, None, False, "hopeful"),
    ("SP-IJ-TRI", "Inkjet Cartridge - Tri-color", "Supplies", "Consumer", "supplies", "SUP04", 26000, -0.15, .12, 100, 760, 1149, None, None, False, "hopeful"),
    ("SP-TN-STD", "Toner Cartridge - Black (Std)", "Supplies", "Commercial", "supplies", "SUP04", 14000, 0.02, .14, 50, 3600, 5200, None, None, False, "none"),
    ("SP-TN-HY", "Toner Cartridge - Black (High Yield)", "Supplies", "Commercial", "supplies", "SUP04", 6500, 0.08, .14, 50, 5400, 7700, None, None, False, "none"),
    ("SP-TN-CLR", "Color Toner Set", "Supplies", "Commercial", "supplies", "SUP04", 900, 0.04, .25, 10, 21000, 29500, None, None, True, "none"),
    ("AC-MSE-WL", "Wireless Mouse", "Accessories", "Consumer", "mixed", "SUP05", 22000, 0.05, .30, 100, 420, 699, None, None, False, "none"),
    ("AC-KBM-CMB", "Wireless Keyboard & Mouse Combo", "Accessories", "Consumer", "mixed", "SUP05", 9000, 0.05, .30, 50, 1150, 1799, None, None, False, "none"),
    ("AC-BAG-156", "Laptop Backpack 15.6", "Accessories", "Consumer", "consumer", "SUP05", 11000, 0.03, .30, 50, 650, 1199, None, None, False, "none"),
    ("AC-DOCK-C", "USB-C Dock", "Accessories", "Commercial", "commercial", "SUP05", 1600, 0.18, .30, 20, 7800, 10900, None, None, False, "none"),
]
PCOLS = ["SKU", "ProductName", "Category", "Segment", "x_season", "SupplierID", "x_base", "x_growth", "x_cv",
         "CasePack", "UnitCostINR", "ListPriceINR", "x_launch", "x_eol", "x_metro_only", "x_bias"]
PRODUCTS = pd.DataFrame(P, columns=PCOLS)


def has(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def lifecycle_status(r) -> str:
    if has(r.x_eol):
        return "EOL"
    if has(r.x_launch) and r.x_launch >= t_of(pd.Timestamp("2025-11-01")):
        return "NPI"
    if r.x_growth >= 0.10 or (has(r.x_launch)):
        return "Growth"
    if r.x_growth <= -0.10:
        return "Declining"
    return "Mature"


PRODUCTS["LifecycleStatus"] = [lifecycle_status(r) for r in PRODUCTS.itertuples()]
PRODUCTS["LaunchDate"] = [
    MONTHS[int(r.x_launch)].strftime("%Y-%m-%d") if has(r.x_launch) else "2023-04-01"
    for r in PRODUCTS.itertuples()
]

# --------------------------------------------------------------------------------------
# Demand model
# --------------------------------------------------------------------------------------
DEAL_P, FALSE_DEAL_P, DEAL_KNOWN_P = 0.08, 0.03, 0.75
FESTIVE_BIAS = {9: 1.15, 10: 1.25, 11: 1.20}


def dc_drift(loc: str, t: int) -> float:
    if loc == "DC05" and t >= 26:  # Hyderabad: new e-commerce fulfilment hub from Jan 2026
        return 1.025 ** (t - 25)
    if loc == "DC06" and t >= 26:  # Kolkata: a large distributor moved away
        return 0.985 ** (t - 25)
    return 1.0


def lifecycle(p, t: int) -> float:
    f = 1.0
    if has(p.x_launch):
        if t < p.x_launch:
            return 0.0
        f = min(1.0, (t - p.x_launch + 1) / 4)
    if has(p.x_eol) and t >= p.x_eol:
        f *= max(0.08, 1 - 0.18 * (t - p.x_eol + 1))
    return f


def mu(p, loc_share: float, loc: str, t: int) -> float:
    m = MONTHS[t].month
    growth = (1 + p.x_growth) ** ((t - T_OUT) / 12)
    return p.x_base * loc_share * dc_drift(loc, t) * SEASON[p.x_season][m] * growth * lifecycle(p, t)


def gamma_poisson(m: float, cv: float) -> int:
    if m <= 0:
        return 0
    k = 1 / cv ** 2
    return int(rng.poisson(rng.gamma(k, m / k)))


# --------------------------------------------------------------------------------------
# Simulation per SKU x DC series
# --------------------------------------------------------------------------------------
ALPHA, Z, SS_FLOOR_MONTHS = 0.25, 1.4, 0.45
DISRUPT_START, DISRUPT_END = pd.Timestamp("2026-07-20"), pd.Timestamp("2026-10-31")

rows_demand, rows_fcst, rows_inv, rows_lots, rows_po = [], [], [], [], []
po_counter = 0


def new_po_id() -> str:
    global po_counter
    po_counter += 1
    return f"PO{po_counter:06d}"


for p in PRODUCTS.itertuples():
    sup = SUP.loc[p.SupplierID]
    lt_m = int(sup.x_lt_months)
    locs = LOCATIONS[LOCATIONS.LocationID.isin(METRO)] if p.x_metro_only else LOCATIONS
    share_total = locs.x_share.sum()
    for loc in locs.itertuples():
        share = loc.x_share / share_total
        L = loc.LocationID
        # ---- true demand, deals --------------------------------------------------------
        mus = np.array([mu(p, share, L, t) for t in range(T_SIM + 1)])
        deal = np.zeros(T_SIM + 1)
        deal_known = np.zeros(T_SIM + 1)
        if p.x_bias == "deals":
            for t in range(T_SIM + 1):
                if rng.random() < DEAL_P:
                    deal[t] = rng.uniform(0.5, 1.5) * mus[t]
                    if rng.random() < DEAL_KNOWN_P:
                        deal_known[t] = deal[t] * rng.uniform(0.8, 1.1)
                elif rng.random() < FALSE_DEAL_P:
                    deal_known[t] = rng.uniform(0.5, 1.0) * mus[t]  # slipped / lost deal
        actual = np.array([gamma_poisson(mus[t], p.x_cv) + int(round(deal[t])) for t in range(T_LAST + 1)])

        # ---- statistical forecast: seasonal exponential smoothing of the level ----------
        s_model = {m: SEASON[p.x_season][m] * (1 + rng.normal(0, 0.03)) for m in range(1, 13)}
        level = np.zeros(T_LAST + 1)
        prev = mus[0] / SEASON[p.x_season][MONTHS[0].month] if mus[0] > 0 else 0.0
        for t in range(T_LAST + 1):
            s = s_model[MONTHS[t].month]
            if prev == 0 and actual[t] > 0:   # first month of sales for an NPI
                prev = actual[t] / s
            else:
                prev = ALPHA * actual[t] / s + (1 - ALPHA) * prev
            level[t] = prev

        def stat(made: int, k: int) -> float:
            """statistical forecast for month k, produced after observing month `made`."""
            if made < 0:
                return mus[k]
            return level[made] * s_model[MONTHS[k].month]

        view_cache: dict[tuple[int, int], float] = {}

        def view(made: int, k: int) -> float:
            """consensus (planner) forecast for month k, produced after observing month `made`."""
            key = (made, k)
            if key in view_cache:
                return view_cache[key]
            f = stat(made, k)
            m = MONTHS[k].month
            if p.x_bias == "festive":
                f *= FESTIVE_BIAS.get(m, 1.03)
            elif p.x_bias == "conservative":
                f *= 0.98
            elif p.x_bias == "hopeful":
                f *= 1.12
            f += deal_known[k]
            launch = p.x_launch if has(p.x_launch) else None
            if launch is not None and k >= launch and k < launch + 6:
                f = mus[k] * rng.uniform(0.9, 1.2)  # launch plan beats a stat model with no history
            if launch is not None and k < launch:
                f = 0.0
            eol = p.x_eol if has(p.x_eol) else None
            if eol is not None and k >= eol:
                f *= 1.10 if made < eol + 2 else 0.80  # forecast only cut at the July review
            f *= 1 + rng.normal(0, 0.04)
            f = max(0.0, f)
            view_cache[key] = f
            return f

        stat_fc = {k: (0.0 if (has(p.x_launch) and level[min(k - 1, T_LAST)] == 0) else stat(min(k - 1, T_LAST), k)) for k in range(T_OUT, T_END + 1)}
        cons_fc = {k: view(min(k - 1, T_LAST), k) for k in range(T_OUT, T_END + 1)}

        # ---- replenishment simulation ----------------------------------------------------
        cv_err = p.x_cv + 0.08
        init_cover = sum(mus[k] for k in range(0, lt_m + 1))
        init_ss = max(Z * cv_err * (init_cover / (lt_m + 1)) * math.sqrt(lt_m + 1), SS_FLOOR_MONTHS * init_cover / (lt_m + 1))
        oh = int(round(init_cover + init_ss))
        lots = deque()
        if oh > 0:
            lots.append(["INIT", pd.Timestamp("2023-10-15"), oh])
        pipeline = []  # dicts for each PO line
        for t in range(T_END):
            is_planned = t > T_LAST
            made = t - 1
            # projected on-hand for planned months
            window = [view(made if made <= T_LAST else T_LAST, k) for k in range(t, t + lt_m + 1)]
            ss = max(Z * cv_err * np.mean(window) * math.sqrt(lt_m + 1), SS_FLOOR_MONTHS * np.mean(window))
            on_order = sum(po["_qty_eff"] for po in pipeline if po["_arr_t"] >= t)
            ip = oh + on_order
            q = sum(window) + ss - ip
            if q > 0 and sum(window) > 0:
                q = int(math.ceil(q / p.CasePack) * p.CasePack)
                po_date = MONTHS[t] + pd.Timedelta(days=int(rng.integers(0, 6)))
                req = po_date + pd.Timedelta(days=int(sup.StdLeadTimeDays))
                if is_planned:
                    delay, rec_qty = 0, q
                else:
                    delay = int(round(rng.normal(sup.x_delay_mu, sup.x_delay_sd)))
                    delay = max(delay, -7)
                    if p.SupplierID == "SUP01" and DISRUPT_START <= req <= DISRUPT_END and rng.random() < 0.85:
                        delay = int(rng.integers(20, 51))
                    rec_qty = q if rng.random() > 0.03 else int(round(q * rng.uniform(0.8, 0.95)))
                arr = req + pd.Timedelta(days=delay)
                pipeline.append(dict(PO_Line_ID=new_po_id(), PO_Date=po_date, SKU=p.SKU, LocationID=L,
                                     OrderQty=q, RequestedDate=req, _arrival=arr, _rec_qty=rec_qty,
                                     _arr_t=t_of(arr), _qty_eff=rec_qty, _planned=is_planned))
            if t > T_LAST:
                # future month: project on-hand with forecast (used for the next planned order)
                rec = sum(po["_rec_qty"] for po in pipeline if po["_arr_t"] == t)
                oh = max(0, oh + rec - int(round(view(T_LAST, t))))
                continue
            # ---- execute month t --------------------------------------------------------
            opening = oh
            arrivals = sorted([po for po in pipeline if po["_arr_t"] == t], key=lambda x: x["_arrival"])
            receipts = 0
            for po in arrivals:
                receipts += po["_rec_qty"]
                if po["_rec_qty"] > 0:
                    lots.append([po["PO_Line_ID"], po["_arrival"].normalize(), po["_rec_qty"]])
            avail = opening + receipts
            demand = int(actual[t])
            shipped = min(demand, avail)
            unfilled = demand - shipped
            oh = avail - shipped
            # FIFO consumption
            need = shipped
            while need > 0 and lots:
                take = min(need, lots[0][2])
                lots[0][2] -= take
                need -= take
                if lots[0][2] == 0:
                    lots.popleft()
            if t >= T_OUT:
                me = month_end(t)
                rows_inv.append((me.date(), p.SKU, L, opening, receipts, shipped, unfilled, oh, int(round(ss))))
                rows_demand.append((MONTHS[t].date(), p.SKU, L, demand))
                for lot_id, rdate, qty in lots:
                    if qty > 0:
                        rows_lots.append((me.date(), p.SKU, L, lot_id, rdate.date(), qty))
        # ---- export PO lines ---------------------------------------------------------------
        for po in pipeline:
            received = (not po["_planned"]) and po["_arrival"] <= AS_OF
            if received and po["_arrival"] < MONTHS[T_OUT]:
                continue  # received before the reporting window
            if po["_planned"]:
                status = "Planned"
            elif received:
                status = "Received"
            else:
                status = "Open"
            rows_po.append(dict(
                PO_Line_ID=po["PO_Line_ID"], PO_Date=po["PO_Date"], SupplierID=p.SupplierID, SKU=p.SKU,
                LocationID=L, OrderQty=po["OrderQty"], RequestedDate=po["RequestedDate"],
                ReceiptDate=po["_arrival"] if received else pd.NaT,
                ReceivedQty=po["_rec_qty"] if received else None,
                Status=status,
                SupplierETA=pd.NaT if received else po["_arrival"],
            ))
        # ---- export forecasts ---------------------------------------------------------------
        for k in range(T_OUT, T_END + 1):
            rows_fcst.append((p.SKU, L, MONTHS[k].strftime("%Y-%m"), int(round(stat_fc[k])), int(round(cons_fc[k]))))

# --------------------------------------------------------------------------------------
# Write raw files
# --------------------------------------------------------------------------------------
SUPPLIERS.drop(columns=[c for c in SUPPLIERS.columns if c.startswith("x_")]).to_csv(RAW / "suppliers.csv", index=False)
LOCATIONS.drop(columns=["x_share"]).to_csv(RAW / "locations.csv", index=False)
PRODUCTS[["SKU", "ProductName", "Category", "Segment", "LifecycleStatus", "LaunchDate", "SupplierID",
          "UnitCostINR", "ListPriceINR", "CasePack"]].to_csv(RAW / "products.csv", index=False)

pd.DataFrame(rows_demand, columns=["Month", "SKU", "LocationID", "DemandUnits"]).to_csv(RAW / "demand_actuals.csv", index=False)

fc = pd.DataFrame(rows_fcst, columns=["SKU", "LocationID", "Month", "Statistical", "Consensus"])
fc_long = fc.melt(id_vars=["SKU", "LocationID", "Month"], var_name="ForecastType", value_name="Units")
fc_wide = fc_long.pivot_table(index=["SKU", "LocationID", "ForecastType"], columns="Month", values="Units", aggfunc="sum").reset_index()
fc_wide.columns.name = None
fc_wide.to_csv(RAW / "forecast_plan_wide.csv", index=False)

pd.DataFrame(rows_inv, columns=["SnapshotDate", "SKU", "LocationID", "OpeningUnits", "ReceiptUnits", "ShippedUnits",
                                "UnfilledUnits", "ClosingUnits", "SafetyStockUnits"]).to_csv(RAW / "inventory_monthly.csv", index=False)
pd.DataFrame(rows_lots, columns=["SnapshotDate", "SKU", "LocationID", "LotID", "ReceiptDate", "UnitsOnHand"]).to_csv(RAW / "inventory_lots.csv", index=False)

# purchase orders: exported from an ERP with Indian date format (dd-mm-yyyy), a few badly
# keyed SKU codes and some duplicated lines - to be cleaned in Power Query.
po = pd.DataFrame(rows_po).sort_values(["PO_Date", "PO_Line_ID"]).reset_index(drop=True)
for c in ["PO_Date", "RequestedDate", "ReceiptDate", "SupplierETA"]:
    po[c] = po[c].apply(lambda d: "" if pd.isna(d) else d.strftime("%d-%m-%Y"))
po["ReceivedQty"] = po["ReceivedQty"].apply(lambda v: "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(int(v)))
messy = rng.choice(po.index, size=int(len(po) * 0.02), replace=False)
for i in messy:
    po.at[i, "SKU"] = rng.choice([po.at[i, "SKU"].lower(), " " + po.at[i, "SKU"], po.at[i, "SKU"] + "  "])
dups = po.loc[rng.choice(po.index, size=14, replace=False)].copy()
dups["SKU"] = dups["SKU"].str.strip().str.upper()
po = pd.concat([po, dups]).sort_values(["PO_Line_ID"], kind="stable").reset_index(drop=True)
po.to_csv(RAW / "purchase_orders.csv", index=False)

print("demand rows", len(rows_demand), "| forecast rows (wide)", len(fc_wide), "| inventory rows", len(rows_inv),
      "| lot rows", len(rows_lots), "| PO lines", len(po))
