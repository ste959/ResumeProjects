-- Staging for OMS executions (fills). One row per fill; the grain of fct_fills.

with source as (
    select * from {{ source('oms', 'execution') }}
)

select
    id           as execution_id,
    order_id,
    quantity     as fill_quantity,
    price        as fill_price,
    upper(venue) as venue,
    executed_at  as filled_at
from source
