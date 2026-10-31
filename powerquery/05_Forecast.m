// STAGING query - untick "Enable load".
// The planning system exports forecasts WIDE (one column per month). Unpivot to long,
// then pivot ForecastType so Statistical and Consensus sit side by side.
let
    Source     = Csv.Document(File.Contents(DataFolder & "forecast_plan_wide.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted   = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Unpivoted  = Table.UnpivotOtherColumns(Promoted, {"SKU", "LocationID", "ForecastType"}, "MonthText", "Units"),
    AddMonth   = Table.AddColumn(Unpivoted, "Month", each Date.FromText([MonthText] & "-01"), type date),
    TypedUnits = Table.TransformColumnTypes(AddMonth, {{"Units", Int64.Type}}),
    Removed    = Table.RemoveColumns(TypedUnits, {"MonthText"}),
    Pivoted    = Table.Pivot(Removed, List.Distinct(Removed[ForecastType]), "ForecastType", "Units"),
    Renamed    = Table.RenameColumns(Pivoted, {{"Statistical", "StatForecastUnits"}, {"Consensus", "ConsensusForecastUnits"}})
in
    Renamed
