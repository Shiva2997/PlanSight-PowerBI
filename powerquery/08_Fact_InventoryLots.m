// Month-end stock by receipt lot (FIFO) -> age in days and ageing buckets
let
    Source    = Csv.Document(File.Contents(DataFolder & "inventory_lots.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted  = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed     = Table.TransformColumnTypes(Promoted, {
                    {"SnapshotDate", type date}, {"SKU", type text}, {"LocationID", type text},
                    {"LotID", type text}, {"ReceiptDate", type date}, {"UnitsOnHand", Int64.Type}}),
    AddAge    = Table.AddColumn(Typed, "AgeDays", each Duration.Days([SnapshotDate] - [ReceiptDate]), Int64.Type),
    AddBucket = Table.AddColumn(AddAge, "AgeBucket", each
                    if [AgeDays] <= 30 then "0-30 days"
                    else if [AgeDays] <= 60 then "31-60 days"
                    else if [AgeDays] <= 90 then "61-90 days"
                    else if [AgeDays] <= 180 then "91-180 days"
                    else "180+ days", type text),
    AddSort   = Table.AddColumn(AddBucket, "AgeBucketSort", each
                    if [AgeDays] <= 30 then 1
                    else if [AgeDays] <= 60 then 2
                    else if [AgeDays] <= 90 then 3
                    else if [AgeDays] <= 180 then 4
                    else 5, Int64.Type)
in
    AddSort
