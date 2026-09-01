-- Staging for OMS orders: rename to analytics-friendly names, normalize enum casing,
-- and expose only the columns the marts need. No business logic here by design.

with source as (
    select * from {{ source('oms', 'orders') }}
)

select
    id                    as order_id,
    order_ref,
    cusip,
    portfolio,
    trader,
    upper(side)           as side,
    upper(order_type)     as order_type,
    upper(time_in_force)  as time_in_force,
    quantity              as ordered_quantity,
    limit_price,
    upper(status)         as status,
    filled_quantity,
    avg_fill_price,
    status_reason,
    created_at            as order_created_at,
    updated_at            as order_updated_at
from source
