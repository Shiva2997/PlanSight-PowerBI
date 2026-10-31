// Month-end stock ledger per SKU x DC
let
    Source   = Csv.Document(File.Contents(DataFolder & "inventory_monthly.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                   {"SnapshotDate", type date}, {"SKU", type text}, {"LocationID", type text},
                   {"OpeningUnits", Int64.Type}, {"ReceiptUnits", Int64.Type}, {"ShippedUnits", Int64.Type},
                   {"UnfilledUnits", Int64.Type}, {"ClosingUnits", Int64.Type}, {"SafetyStockUnits", Int64.Type}})
in
    Typed
