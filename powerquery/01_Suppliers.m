// STAGING query - right-click > untick "Enable load" (it is merged into Dim_Product)
let
    Source   = Csv.Document(File.Contents(DataFolder & "suppliers.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                   {"SupplierID", type text}, {"SupplierName", type text}, {"SupplierCountry", type text},
                   {"StdLeadTimeDays", Int64.Type}, {"ShipMode", type text}})
in
    Typed
