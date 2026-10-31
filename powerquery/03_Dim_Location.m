let
    Source   = Csv.Document(File.Contents(DataFolder & "locations.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                   {"LocationID", type text}, {"DCName", type text}, {"City", type text}, {"State", type text},
                   {"Region", type text}, {"DCType", type text}, {"Latitude", type number}, {"Longitude", type number}},
                   "en-US")
in
    Typed
