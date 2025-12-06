select 
    player_name
    , yas_position
    , draft_year
    , measurables_present
    , yas_score
from 
    "gridiron_yampylytics"."yas"."yas_complete"
where 
    calculation_position = yas_position 
    and calculation_type = 'current' 
    and measurables_present >= 5
order by 
    yas_score desc
