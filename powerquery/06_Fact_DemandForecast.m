// One row per Month x SKU x DC: stat forecast, consensus forecast and actual demand.
// Future months (Nov-26 to Jan-27) have forecasts but no actuals (HasActual = false).
let
    Source     = Forecast,
    Merged     = Table.NestedJoin(Source, {"Month", "SKU", "LocationID"}, Actuals, {"Month", "SKU", "LocationID"}, "Act", JoinKind.LeftOuter),
    Expanded   = Table.ExpandTableColumn(Merged, "Act", {"DemandUnits"}, {"ActualUnits"}),
    LastActual = List.Max(Actuals[Month]),
    AddHas     = Table.AddColumn(Expanded, "HasActual", each [Month] <= LastActual, type logical),
    Typed      = Table.TransformColumnTypes(AddHas, {
                     {"StatForecastUnits", Int64.Type}, {"ConsensusForecastUnits", Int64.Type}, {"ActualUnits", Int64.Type}})
in
    Typed
