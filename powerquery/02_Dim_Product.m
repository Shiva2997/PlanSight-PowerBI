// Product dimension, with supplier attributes merged in (snowflake -> star)
let
    Source   = Csv.Document(File.Contents(DataFolder & "products.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                   {"SKU", type text}, {"ProductName", type text}, {"Category", type text}, {"Segment", type text},
                   {"LifecycleStatus", type text}, {"LaunchDate", type date}, {"SupplierID", type text},
                   {"UnitCostINR", Int64.Type}, {"ListPriceINR", Int64.Type}, {"CasePack", Int64.Type}}),
    Merged   = Table.NestedJoin(Typed, {"SupplierID"}, Suppliers, {"SupplierID"}, "Sup", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Merged, "Sup",
                   {"SupplierName", "SupplierCountry", "StdLeadTimeDays"},
                   {"SupplierName", "SupplierCountry", "StdLeadTimeDays"})
in
    Expanded
