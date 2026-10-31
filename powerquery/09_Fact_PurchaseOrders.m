// ERP purchase-order export. Cleaning steps:
//   1. SKU codes keyed inconsistently (lower case / extra spaces) -> Trim + Upper
//   2. 14 duplicated lines from a double export                   -> Remove duplicates
//   3. Blank dates/quantities on open lines                       -> null
//   4. Dates are Indian format dd-mm-yyyy                         -> change type using locale en-IN
//   5. Derived columns for supplier KPIs and the shortage projection
let
    Source        = Csv.Document(File.Contents(DataFolder & "purchase_orders.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted      = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    CleanSKU      = Table.TransformColumns(Promoted, {{"SKU", each Text.Upper(Text.Trim(_)), type text}}),
    Dedup         = Table.Distinct(CleanSKU),
    BlankToNull   = Table.ReplaceValue(Dedup, "", null, Replacer.ReplaceValue, {"ReceiptDate", "ReceivedQty", "SupplierETA"}),
    TypedDates    = Table.TransformColumnTypes(BlankToNull, {
                        {"PO_Date", type date}, {"RequestedDate", type date}, {"ReceiptDate", type date}, {"SupplierETA", type date}},
                        "en-IN"),
    Typed         = Table.TransformColumnTypes(TypedDates, {
                        {"PO_Line_ID", type text}, {"SupplierID", type text}, {"LocationID", type text}, {"Status", type text},
                        {"OrderQty", Int64.Type}, {"ReceivedQty", Int64.Type}}),
    AddExpected   = Table.AddColumn(Typed, "ExpectedReceiptDate", each if [Status] = "Received" then [ReceiptDate] else [SupplierETA], type date),
    AddOpenQty    = Table.AddColumn(AddExpected, "OpenQty", each if [Status] = "Received" then 0 else [OrderQty], Int64.Type),
    AddDelay      = Table.AddColumn(AddOpenQty, "DelayDays", each if [Status] = "Received" then Duration.Days([ReceiptDate] - [RequestedDate]) else null, Int64.Type),
    AddOnTime     = Table.AddColumn(AddDelay, "OnTimeFlag", each if [Status] = "Received" then (if [DelayDays] <= 3 then 1 else 0) else null, Int64.Type),
    AddInFull     = Table.AddColumn(AddOnTime, "InFullFlag", each if [Status] = "Received" then (if [ReceivedQty] >= [OrderQty] then 1 else 0) else null, Int64.Type)
in
    AddInFull
