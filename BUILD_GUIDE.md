# PlanSight: Build Guide

This guide walks you through building the PlanSight dashboard in Power BI from the raw files. Budget about **6–8 hours**; a weekend is enough. Every step has a checkpoint, so you'll know straight away if something is off.

> **Why build it yourself instead of opening a finished file?** Interviewers ask *how* you built it: "why WAPE and not MAPE?", "how did you handle the wide forecast file?", "why can't you sum inventory across months?". Doing each step yourself is what lets you answer.

**Contents**
0. [Before you start](#0-before-you-start)
1. [Load and clean the data in Power Query](#1-load-and-clean-the-data-in-power-query-about-90-min)
2. [Build the data model](#2-build-the-data-model-about-30-min)
3. [Create the DAX measures](#3-create-the-dax-measures-about-90-min)
4. [Build the four report pages](#4-build-the-four-report-pages-about-3-h)
5. [Find and write your insights](#5-find-and-write-your-insights-about-30-min)
6. [Publish to GitHub](#6-publish-to-github-about-30-min)
7. [Interview prep](#7-interview-prep)
8. [Resume and application text](#8-resume-and-application-text)
9. [Troubleshooting](#9-troubleshooting)

---

## 0. Before you start

**Software.** Power BI Desktop is free, but it runs **only on Windows** (install it from the Microsoft Store).

**If you're on a Mac**, pick one of these:
- **A Windows PC** (a college computer lab or a friend's laptop). This is the easiest option. Carry the project folder on a USB stick or in Google Drive.
- **A Windows virtual machine** on your Mac, for example Parallels Desktop running Windows 11.
- **Power BI in the browser** (app.powerbi.com) has limited editing and can't run the Power Query steps on local files. Use it only to *view or share* the finished report, not to build it.

**Set up the folder.** Unzip the project to a short path with no spaces, for example `C:\PlanSight-PowerBI\`.

**What you're building.** Four pages. The mockups in `docs/mockups/` show the target layout, drawn from the same data you'll load, so your numbers should match them.

| Page | Answers the question | Mockup |
|---|---|---|
| Overview | How is planning performing overall? | `page1_overview.png` |
| Demand & Forecast | How good is the forecast, and do planner overrides help? | `page2_demand_forecast.png` |
| Inventory Health | Where is stock short, excess or ageing? | `page3_inventory_health.png` |
| Supply & Shortage Risk | Which suppliers are late, and what will run out in the next 3 months? | `page4_supply_risk.png` |

**The business context.** A PC and printing company runs 8 distribution centres (DCs) in India. Data covers FY25–FY26; its fiscal year runs **November to October**, so FY26 = Nov 2025 to Oct 2026. Today is **31 Oct 2026**. You have 24 months of history plus a 3-month forward forecast (Nov 2026 to Jan 2027).

---

## 1. Load and clean the data in Power Query (about 90 min)

Open Power BI Desktop, then go to **Home → Transform data** to open the Power Query Editor.

For each query below you can **click through the steps** (better for learning), or create a **Blank Query** (Home → New Source → Blank Query), open **Advanced Editor**, paste the code from the matching `powerquery/*.m` file, and rename the query. Use the exact query names, because later queries refer to them.

### 1.1 Parameter: `DataFolder`
Go to **Home → Manage Parameters → New Parameter** and set:
- Name: `DataFolder`
- Type: Text
- Current value: `C:\PlanSight-PowerBI\data\raw\` (your own path, **with the trailing backslash**)

### 1.2 Dimensions
| Query | File | What to do |
|---|---|---|
| `Suppliers` | `01_Suppliers.m` | Load the CSV and set the types. **Staging only**: right-click → untick **Enable load**. |
| `Dim_Product` | `02_Dim_Product.m` | **Merge Queries** with `Suppliers` on `SupplierID` (left outer), then expand `SupplierName`, `SupplierCountry` and `StdLeadTimeDays`. This flattens a snowflake into a star schema. |
| `Dim_Location` | `03_Dim_Location.m` | Load the CSV and set the types. |

### 1.3 Demand and forecast
| Query | File | What to do |
|---|---|---|
| `Actuals` | `04_Actuals.m` | Load the CSV and set the types. Staging only (untick Enable load). |
| `Forecast` | `05_Forecast.m` | The planning-system export is **wide**, with one column per month. Select `SKU`, `LocationID` and `ForecastType`, then **Transform → Unpivot Other Columns**. Add a `Month` column from the text (`Date.FromText([MonthText] & "-01")`). Then select `ForecastType` and use **Transform → Pivot Column** (values = `Units`, *Advanced: Don't aggregate*). Rename the results to `StatForecastUnits` and `ConsensusForecastUnits`. Staging only. |
| `Fact_DemandForecast` | `06_Fact_DemandForecast.m` | Start from `Forecast` and **Merge Queries** with `Actuals` on Month + SKU + LocationID (select the three columns in the same order on both sides, left outer). Expand `DemandUnits` as `ActualUnits`. Add a `HasActual` column that is true for months up to the last actual month. |

### 1.4 Inventory
| Query | File | What to do |
|---|---|---|
| `Fact_Inventory` | `07_Fact_Inventory.m` | Month-end stock ledger. Set the types. |
| `Fact_InventoryLots` | `08_Fact_InventoryLots.m` | Add a custom column `AgeDays = Duration.Days([SnapshotDate] - [ReceiptDate])`. Add a **Conditional Column** `AgeBucket` (0-30 / 31-60 / 61-90 / 91-180 / 180+ days) and `AgeBucketSort` (1–5). |

### 1.5 Purchase orders (the messy one)
`Fact_PurchaseOrders` comes from `09_Fact_PurchaseOrders.m`. It's a realistic ERP export with problems to fix:
1. **SKU codes keyed inconsistently.** About 140 rows are in lower case or have extra spaces. Use **Transform → Format → Trim**, then **Format → UPPERCASE**.
2. **14 duplicated lines** from a double export. Use **Home → Remove Rows → Remove Duplicates** (with all columns selected).
3. **Blank dates and quantities** on open PO lines. Use **Replace Values** to turn `""` into `null`.
4. **Indian date format (dd-mm-yyyy).** If you just change the type to Date, `02-11-2024` can become *11 Feb* on a US-locale PC. Right-click the column → **Change Type → Using Locale… → Date, English (India)**.
5. **Derived columns:** `ExpectedReceiptDate`, `OpenQty`, `DelayDays`, `OnTimeFlag` (on time = received no more than 3 days after the requested date) and `InFullFlag`.

### 1.6 Close & Apply
Check that `Suppliers`, `Actuals` and `Forecast` have **Enable load** unticked, then choose **Home → Close & Apply**.

**✅ Checkpoint: row counts** (Data view, bottom-left of each table)
| Table | Rows |
|---|---|
| Dim_Product | 37 |
| Dim_Location | 8 |
| Fact_DemandForecast | 7,749 |
| Fact_Inventory | 6,888 |
| Fact_InventoryLots | 10,011 |
| Fact_PurchaseOrders | 7,061 (the raw file has 7,075; the 14 duplicates are removed) |

> **Stuck?** The `data/clean/` folder holds the same six tables already cleaned. You can load those with **Get data → Text/CSV** and jump to step 2. Try the raw route first, though, because the cleaning steps are good interview material.

---

## 2. Build the data model (about 30 min)

### 2.1 Calculated tables
Go to **Modeling → New table** and paste the `Date` and `Dim_Status` definitions from `dax/measures.dax`. Then:
- Select `Date` and choose **Table tools → Mark as date table**, using the `Date` column. **Don't skip this**: the time-intelligence and forward-forecast measures depend on it.
- In Data view, set **Sort by column** for these columns:
  - `YearMonth` by `YearMonthSort`
  - `MonthName` by `FiscalMonthNum`
  - `Dim_Status[Status]` by `SortOrder`
  - `Fact_InventoryLots[AgeBucket]` by `AgeBucketSort`

### 2.2 Relationships (Model view)
All relationships are **many-to-one (*:1)** with **single** cross-filter direction:

| From (many) | To (one) |
|---|---|
| Fact_DemandForecast[Month] | Date[Date] |
| Fact_Inventory[SnapshotDate] | Date[Date] |
| Fact_InventoryLots[SnapshotDate] | Date[Date] |
| Fact_PurchaseOrders[RequestedDate] | Date[Date] |
| each fact [SKU] | Dim_Product[SKU] |
| each fact [LocationID] | Dim_Location[LocationID] |

`Dim_Status` stays **disconnected** on purpose. Delete any relationships Power BI auto-created that aren't in this table.

### 2.3 Tidy up
- Use **Home → Enter data** to create a table named `_Measures` (you'll put all measures here). After the first measure is added, delete its dummy column.
- Hide the key columns in fact tables (`SKU`, `LocationID`, date keys) so report builders use the dimensions instead.
- Take a screenshot of the Model view for your README (`docs/screenshots/model.png`).

**✅ Checkpoint:** Model view shows a star: 4 facts in the middle, `Date`, `Dim_Product` and `Dim_Location` around them, and `Dim_Status` on its own.

---

## 3. Create the DAX measures (about 90 min)

Select `_Measures`, choose **Modeling → New measure**, and paste each measure from `dax/measures.dax` **in the order they appear**, because later measures use earlier ones. Read the comment above each one; that's your interview explanation.

**Formats** (Measure tools ribbon):
| Measures | Format |
|---|---|
| All `%` measures | Percentage, 1 decimal |
| `Forecast Bias %`, `Stat Bias %`, `Demand Growth YoY %` | Custom `+0.0%;-0.0%;0.0%` |
| `Forecast Value Add (pts)` | Custom `+0.0" pts";-0.0" pts";0.0" pts"` |
| Units and counts | Whole number, thousands separator |
| `(₹ Cr)` measures, `Weeks of Supply`, `Avg Delay Days` | Decimal, 1 place |

Optionally, group measures into the display folders named in the file (Model view → Properties → Display folder).

**✅ Checkpoint: build a test page.** Add a Fiscal Year slicer set to **FY26** and drop these measures into cards. They should match:

| Measure | Expected |
|---|---|
| Actual Units | 3,556,222 |
| Demand Value (₹ Cr) | 3,403.6 |
| Demand Growth YoY % | +7.7% |
| Forecast Accuracy % | 81.7% |
| Stat Forecast Accuracy % | 83.1% |
| Forecast Value Add (pts) | -1.5 pts |
| Forecast Bias % | +0.0% |
| Fill Rate % | 98.7% |
| Stockout Events | 220 |
| Lost Sales Value (₹ Cr) | 85.1 |
| Inventory Value (₹ Cr) | 312.9 |
| Weeks of Supply | 3.7 |
| Excess Value (₹ Cr) | 45.3 |
| Aged >90d Value (₹ Cr) | 30.5 |
| Aged >90d % | 9.8% |
| On-Time Delivery % | 84.0% |
| OTIF % | 81.4% |
| Avg Delay Days (Late Lines) | 13.8 |
| Past-Due Open PO Lines | 36 |
| Shortage Risk SKU-DCs | 12 |
| Projected Shortage Units | 1,682 |

**Forecast accuracy by category (FY26):**

| Category | Forecast Accuracy % | Stat Forecast Accuracy % | Forecast Value Add (pts) | Forecast Bias % | Fill Rate % |
|---|---|---|---|---|---|
| Accessories | 76.6% | 76.5% | +0.1 | -0.4% | 98.5% |
| Commercial Notebooks | 75.8% | 73.9% | +1.9 | +1.2% | 98.7% |
| Consumer Notebooks | 72.8% | 70.4% | +2.4 | +12.0% | 95.8% |
| Desktops | 75.2% | 72.5% | +2.7 | +7.1% | 99.3% |
| Monitors | 78.5% | 78.8% | -0.3 | -2.4% | 98.5% |
| Printers | 77.7% | 78.0% | -0.3 | -1.6% | 97.7% |
| Supplies | 84.9% | 87.7% | -2.8 | -0.9% | 99.1% |

**Inventory status counts at Oct-26** (`SKU-DC Count` by `Dim_Status[Status]`): Stocked out 28 · Stockout risk 29 · Healthy 178 · Watch 30 · Excess 22.

If a number is off, see [Troubleshooting](#9-troubleshooting). If yours match to the decimal, your model is right. (`scripts/kpi_reference.py` recomputes all of these independently in Python.)

---

## 4. Build the four report pages (about 3 h)

**Setup, once:**
- **View → Themes → Browse for themes** → `theme/PlanSight-theme.json`.
- Page background: light grey `#F2F4F7`. Visuals: white with rounded corners (Format → General → Effects).
- Header: a dark rectangle (`#1B2A4A`) across the top with the title. Add **Insert → Buttons → Navigator → Page navigator** for the tabs.
- Add slicers to page 1: `Date[FiscalYear]` (dropdown, single select, set to FY26), `Dim_Product[Category]`, `Dim_Location[Region]`, `Dim_Location[DCName]`, `Dim_Product[LifecycleStatus]`. Then use **View → Sync slicers** to sync them to all four pages.
- **Edit interactions:** select the Fiscal Year slicer, choose **Format → Edit interactions**, and click the ⦸ (None) icon on any *trend* visual that should always show the full timeline. Those visuals are marked **(FY slicer: None)** below.

### Page 1: Overview
| Visual | Fields | Notes |
|---|---|---|
| 7 cards | `Forecast Accuracy %`, `Fill Rate %`, `Inventory Value (₹ Cr)`, `Weeks of Supply`, `Aged >90d Value (₹ Cr)`, `On-Time Delivery %`, `Shortage Risk SKU-DCs` | Use the new Card visual and add a reference label for the sub-text (e.g. `Stat Forecast Accuracy %`). |
| Line chart: Demand vs Forecast | X `Date[YearMonth]` · Y `Actual Units`, `Consensus Forecast Units`, `Stat Forecast Units` | **(FY slicer: None).** Make consensus dashed and stat dotted grey. Future months show forecasts only, and the actual line simply stops. |
| Line & clustered column: Fill rate by month | X `YearMonth` · Column `Unfilled Units` · Line `Fill Rate %` | **(FY slicer: None).** Visual filter `Date[IsFuture]` = False. |
| Bar chart | Y `Dim_Product[Category]` · X `Inventory Value (₹ Cr)` | Turn on data labels. |
| Area chart | X `YearMonth` · Y `Inventory Value (₹ Cr)` | **(FY slicer: None).** Filter `IsFuture` = False. |
| Text box: Key insights | Your 3–4 findings from step 5 | Recruiters read this first. |

### Page 2: Demand & Forecast
| Visual | Fields | Notes |
|---|---|---|
| 6 cards | `Forecast Accuracy %`, `Stat Forecast Accuracy %`, `Forecast Value Add (pts)`, `Forecast Bias %`, `Actual Units`, `Demand Growth YoY %` | |
| Clustered bar | Y `Category` · X `Forecast Accuracy %`, `Stat Forecast Accuracy %` | Sort by Forecast Accuracy %. |
| Line chart: Accuracy trend | X `YearMonth` · Y `Forecast Accuracy %`, `Stat Forecast Accuracy %` | **(FY slicer: None).** Filter `IsFuture` = False. Optionally add `Forecast Accuracy % (Rolling 3M)`. |
| Bar: Bias by category | Y `Category` · X `Forecast Bias %` | Bar colour **fx** → Rules: > 0.03 red, < -0.03 amber, otherwise grey. |
| Bar: FVA by category | Y `Category` · X `Forecast Value Add (pts)` | Rules: > 0 green, < 0 red. |
| *Stretch:* matrix | Rows `ProductName` · Columns `Date[FiscalQuarter]` · Values `Forecast Accuracy %` | Background colour scale, red to green. |
| Text box | Findings | |

### Page 3: Inventory Health
| Visual | Fields | Notes |
|---|---|---|
| 6 cards | `Inventory Value (₹ Cr)`, `Weeks of Supply`, `Excess Value (₹ Cr)`, `Aged >90d Value (₹ Cr)`, `SKU-DC Count` ×2 | On the two count cards, add visual filters `Dim_Status[Status]` = "Stocked out" and = "Stockout risk". |
| **Matrix heatmap** (the centrepiece) | Rows `Dim_Product[SKU]` · Columns `Dim_Location[LocationID]` · Values `Weeks of Supply` | Turn off row and column totals. Under **Cell elements → Background color → fx → Format style: Field value → `Status Color`**, then do the same for Font color, or set the font to dark grey. |
| Donut | Legend `Dim_Status[Status]` · Values `SKU-DC Count` | Set slice colours to match Status Color: Stocked out `#B42318`, Stockout risk `#F79009`, Healthy `#12B76A`, Watch `#FEC84B`, Excess `#2E90FA`. |
| Stacked bar: Ageing | Y `Category` · X `Lot Value (₹ Cr)` · Legend `Fact_InventoryLots[AgeBucket]` | |
| Table: Rebalancing | `SKU`, `ProductName`, `Rebalance Opportunity`, `Excess Value (₹ Cr)` | Visual filter: `Rebalance Opportunity` is not blank. |
| Bar: Top excess | Y `ProductName` · X `Excess Value (₹ Cr)` | Filter ProductName → **Top N** = 5 by Excess Value. |

### Page 4: Supply & Shortage Risk
| Visual | Fields | Notes |
|---|---|---|
| 6 cards | `On-Time Delivery %`, `OTIF %`, `Avg Delay Days (Late Lines)`, `Past-Due Open PO Lines`, `Shortage Risk SKU-DCs`, `Projected Shortage Units` | |
| Line chart | X `YearMonth` · Y `On-Time Delivery %` · Legend `Dim_Product[SupplierName]` | Make the China ODM line thick and red. |
| Bar | Y `SupplierName` · X `Avg Delay Days (Late Lines)` | |
| **Matrix: Projected stock** | Rows `Dim_Product[SKU]`, `Dim_Location[DCName]` · Columns `Date[YearMonth]` · Values `Projected Closing Units` | Visual filters: `Date[IsFuture]` = True **and** `Shortage Risk SKU-DCs` is greater than 0. **(FY slicer: None)**, which is essential, otherwise it goes blank. Conditional formatting rules: value < 0 → background `#FEE4E2`, font `#B42318`. Layout: Tabular. |
| Table: Past-due POs | `PO_Line_ID`, `SKU`, `LocationID`, `SupplierName`, `OpenQty`, `RequestedDate`, `ExpectedReceiptDate` | Visual filters: `Status` = Open and `RequestedDate` on or before 31-Oct-2026. Sort by ETA. |
| *Stretch (AI visual):* Decomposition tree | Analyze `Lost Sales Value (₹ Cr)` · Explain by `Category`, `DCName`, `SupplierName`, `ProductName` | Lets you show how ₹85 Cr of lost sales breaks down to its root cause in 4 clicks. Good to demo live. |

**✅ Checkpoint:** compare each page with its mockup. Numbers should match, and colours and layout can be your own.

---

## 5. Find and write your insights (about 30 min)

A dashboard without conclusions is just charts. Use your report to answer the questions below, and write the answers in your own words in the page text boxes and the README. Expected answers are in the collapsible sections, so try first, then check.

**1. Why did service drop in late FY26? Who was hurt, and how much?**
<details><summary>Answer</summary>

The China ODM's on-time delivery fell to **6%** for PO lines due in Aug-26 (29% Sep, 38% Oct). Consumer-notebook fill rate dropped to **73.8% in Aug-26**, and FY26 lost sales on consumer notebooks reached **₹51 Cr** (₹42 Cr in Aug–Oct alone). Use the decomposition tree on Lost Sales to show this.
</details>

**2. Do planner overrides improve the forecast?**
<details><summary>Answer</summary>

Overall, **no**: consensus accuracy is 81.7% vs 83.1% for the stat model (**-1.5 pts FVA**). It depends on the category, though:
- **Supplies lose 2.8 pts.** Demand is stable and overrides only add noise, so these SKUs are candidates for "touchless" (auto-accepted) forecasting.
- **Commercial, desktops and consumer notebooks gain 2–3 pts.** Sales knows about B2B deals, and launch plans for new products beat a stat model with no history.
- **Mature consumer notebooks in festive months (Sep–Nov):** +17% bias and **-6.4 pts FVA**. That's sales optimism. (Check this with Category = Consumer Notebooks, Lifecycle = Mature/Growth, and a month filter.)
</details>

**3. Where is the excess and aged stock, and why?**
<details><summary>Answer</summary>

**₹38.7 Cr of the ₹45.3 Cr excess** and **₹29.9 Cr of the ₹30.5 Cr aged >90 days** sit in one SKU: *Consumer Notebook 14 (Core i3)*, which reached end-of-life in May 2026. Demand fell from ~4,600 units/month to ~500, but the consensus forecast stayed at ~6,000 until July. Late ODM shipments then landed in September, after demand had collapsed. Recommendations: a liquidation or channel promotion, and an EOL "last-time-buy" rule that freezes replenishment once the phase-out is announced.
</details>

**4. Is stock in the right place?**
<details><summary>Answer</summary>

No. **6 notebook SKUs** are in excess in at least one DC and stocked out or at risk in another (see the rebalancing table and heatmap). Transferring stock between DCs is faster and cheaper than a new PO. Separately, **Hyderabad** demand grew **+18.5% YoY** (vs +7.7% for the network) and the forecast didn't keep up (-5.4% bias), so Hyderabad has the lowest fill rate (96.4%) and the most stockout events (41).
</details>

**5. What will run out in the next 3 months?**
<details><summary>Answer</summary>

**12 SKU-DCs** project below zero, a total gap of **1,682 units**, mostly in November. The biggest are wireless mice in Bengaluru and Chennai, ink bottles (black) and ink-tank printers in Hyderabad, and the new Premium Business 13 in Mumbai and Bengaluru. **36 PO lines are already past due.** Actions: expedite the past-due POs, transfer stock from the DCs listed as excess, and raise the Hyderabad forecast.
</details>

---

## 6. Publish to GitHub (about 30 min)

1. **Save** the report as `PlanSight.pbix` in the project root (the file is small, so GitHub accepts it).
2. **Take screenshots** of each page with Windows **Win + Shift + S** and save them in `docs/screenshots/` (`page1.png` … `page4.png`, `model.png`).
3. **Export a PDF** with **File → Export → Export to PDF** and save it as `docs/PlanSight.pdf`. Recruiters without Power BI can open it.
4. In `README.md`, **replace the mockup image links** with your real screenshots, and update the insights if your wording differs.
5. **Create a public repo** called `PlanSight-PowerBI` and upload the whole folder: on github.com, click **Add file → Upload files** and drag everything in. Pin it on your GitHub profile.
6. *Optional:* a 60-second screen recording (Loom or similar) clicking through the pages, linked from the README.

---

## 7. Interview prep

Be ready to answer these in 2–3 sentences each.

**Why WAPE instead of MAPE?**
MAPE explodes on low-volume SKUs, where 2 units forecast against 1 actual is 100% error, and it can't be computed when actual = 0. WAPE weights errors by volume: sum of absolute errors ÷ sum of actuals. I compute the error at SKU × DC × month level *before* summing, so over- and under-forecasts can't cancel out.

**What's Forecast Value Add?**
The accuracy of the final (consensus) forecast minus the accuracy of the statistical baseline. It tells you whether human overrides help. Here they cost 1.5 points overall but add value where planners know something the model can't (deals, launches).

**Why can't you just sum inventory?**
Stock is a *snapshot*, not a flow: adding October's stock to September's double-counts. My measures take the last month-end in the selected period (`Snapshot Date`). Demand and shipments are flows, so they do sum.

**How do you calculate weeks of supply? Why forward-looking?**
Closing stock ÷ (next 3 months' consensus forecast ÷ 13 weeks). Forward-looking because what matters is whether stock covers *upcoming* demand, which differs from past demand in seasonal months and for EOL products.

**How does the shortage projection work?**
On-hand at the as-of date, plus open and planned PO receipts by their ETA, minus cumulative consensus forecast, for each future month and each SKU × DC. Anything negative is a shortage. I count the worst month per SKU × DC so one DC's surplus can't hide another's gap.

**Why a star schema? Why merge suppliers into products?**
Facts in the middle and dimensions around them keep filters simple and fast. Supplier attributes were merged into Dim_Product because each SKU has one supplier. Keeping a separate supplier table would create two filter paths to the PO table, which is ambiguous.

**What did you do in Power Query?**
- Unpivoted a wide planning export (one column per month) and pivoted the forecast types.
- Merged forecasts with actuals.
- Cleaned an ERP extract: trimmed and upper-cased SKU codes, removed 14 duplicate lines, and parsed Indian dd-mm-yyyy dates with locale.
- Derived ageing buckets and delivery-performance flags.

**How did you validate the numbers?**
I reimplemented every KPI independently in Python/pandas (`scripts/kpi_reference.py`) and reconciled card by card. I also checked that the inventory ledger balances (opening + receipts − shipped = closing) and that lot quantities add up to on-hand.

**Is this real HP data?**
No, and say so plainly. It's a synthetic dataset I generated in Python (`scripts/generate_data.py`) to mimic a PC and print supply chain in India, with realistic events built in: an EOL transition, a supplier disruption, festive seasonality and regional demand shifts.

**What would you do next?**
Use weekly buckets instead of monthly, add a safety-stock recommendation by SKU, add channel (retail, e-commerce, B2B) as a dimension, automate the refresh with a scheduled dataflow, and use Copilot or an LLM to draft the monthly demand-review summary from the measures.

---

## 8. Resume and application text

**Resume project entry** (replace the Dynamic Load Balancer project):

> **PlanSight – Supply Chain Planning Dashboard (Power BI)** | GitHub
> - Built a 4-page Power BI dashboard tracking forecast accuracy (WAPE), bias, forecast value add, fill rate, weeks of supply, aged inventory and supplier OTD across 37 SKUs and 8 Indian DCs on a 24-month synthetic dataset generated in Python.
> - Modelled a star schema (4 fact tables, fiscal date table) with 45+ DAX measures, including semi-additive stock measures, inventory-status classification and a 3-month projected-shortage model from open POs and the consensus forecast.
> - Cleaned ERP and planning exports in Power Query: unpivoted wide forecast files, merged forecasts with actuals, de-duplicated PO lines and parsed Indian date formats. Validated every KPI against an independent pandas implementation.
> - Surfaced ₹45 Cr of excess stock (85% in one end-of-life SKU), 12 SKU-DC shortage risks for the next quarter, and negative forecast value add in stable categories, pointing to touchless forecasting.
> - Tech: Power BI, DAX, Power Query (M), Python (pandas, NumPy)

**For the form's "Project/Internship details" box**, describe this project and StockSense together. Both cover demand forecasting, inventory and supply planning, which are exactly the JD's three areas.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `DataFolder` errors / "file not found" | The parameter needs the full path **with a trailing backslash**. |
| PO dates wrong or errors in date columns | Change type **using locale → English (India)**. On a non-Indian PC, a plain type change reads 02-11 as Feb 11. |
| Pivot step error "too many elements" | In Pivot Column → Advanced, choose **Don't aggregate**. Check that `ForecastType` holds only "Statistical" and "Consensus". |
| Forecast Accuracy shows 100% for future months | You're missing the `HasActual = TRUE()` filter inside `Abs Error Consensus`, or `HasActual` wasn't typed as True/False. |
| Weeks of Supply or Fwd 3M Forecast blank with the FY slicer on | `Date` isn't **marked as a date table**, or the relationship to `Fact_DemandForecast[Month]` is missing. |
| Inventory Value far too big (e.g. ₹5,000+ Cr) | You summed `ClosingUnits` across months. Use the `Inventory Value (₹ Cr)` measure, never the raw column. |
| Projected stock matrix blank | The Fiscal Year slicer is filtering it. Set **Edit interactions → None** for that visual, and check the `IsFuture = True` filter. |
| Donut shows one slice / wrong counts | `Dim_Status` must be **disconnected** (no relationships). The legend must use `Dim_Status[Status]`. |
| Ageing buckets in the wrong order | Sort `AgeBucket` by `AgeBucketSort`. |
| Numbers slightly different from the checkpoints | Make sure the FY26 slicer is set and no Category, Region or DC slicer is active. Re-check the duplicate removal (7,061 PO rows). |

To regenerate the data (e.g. with a different random seed), run `python scripts/generate_data.py` and then `python scripts/build_clean.py`.
