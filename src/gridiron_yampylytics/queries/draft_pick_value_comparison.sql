SELECT 
    fs.pick as pick
    , fs.value / 30 as draft_values_fitzgerald_spielberger
    , log10(fs.pick) as log_pick
    , h.value / 5 as draft_values_harvard
    , jj.value / 30 as draft_values_jimmy_johnson
    , rh.value / 10 as draft_values_rich_hill
    , log10(fs.value / 30) * 50 as log_draft_values_fitzgerald_spielberger
    , log10(h.value / 5) * 50 as log_draft_values_harvard
    , log10(jj.value / 30) * 50 as log_draft_values_jimmy_johnson
    , log10(rh.value / 10) * 50 as log_draft_values_rich_hill
FROM 
    reference.draft_values_fitzgerald_spielberger as fs
    JOIN reference.draft_values_harvard as h
    ON fs.pick = h.pick
    JOIN reference.draft_values_jimmy_johnson as jj
    ON fs.pick = jj.pick
    JOIN reference.draft_values_rich_hill as rh
    ON fs.pick = rh.pick