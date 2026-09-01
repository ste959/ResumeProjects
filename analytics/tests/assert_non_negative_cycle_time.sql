-- Data-quality: a fill can never occur before its order was created, so cycle time is
-- non-negative. A negative value means a timestamp is corrupt or the join is wrong. Any row
-- returned fails the build.

select
    execution_id,
    order_id,
    cycle_time_seconds
from {{ ref('fct_fills') }}
where cycle_time_seconds < 0
