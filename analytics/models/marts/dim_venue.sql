-- dim_venue — the execution-venue dimension. One row per venue an order was filled on;
-- the conformed key (venue_key) joins to fct_fills for venue scorecards (the trading analogue
-- of a supplier scorecard).

select distinct
    venue as venue_key,
    venue
from {{ ref('stg_executions') }}
