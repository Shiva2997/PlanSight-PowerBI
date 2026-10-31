// STAGING query - untick "Enable load" (it is merged into Fact_DemandForecast)
let
    Source   = Csv.Document(File.Contents(DataFolder & "demand_actuals.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                   {"Month", type date}, {"SKU", type text}, {"LocationID", type text}, {"DemandUnits", Int64.Type}})
in
    Typed
