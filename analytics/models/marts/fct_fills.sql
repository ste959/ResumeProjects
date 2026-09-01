-- fct_fills — the execution fact table. Grain: one row per fill (execution), enriched with
-- its parent order and the security dimension key, plus the derived operational metric that
-- matters most for a desk: order-to-fill cycle time. This is the base table nearly every KPI
-- and BI view builds on.

with fills as (
    select * from {{ ref('stg_executions') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
)

select
    f.execution_id,
    f.order_id,
    o.order_ref,
    o.cusip                                                as security_key,
    o.portfolio,
    o.trader,
    o.side,
    f.venue,
    f.fill_quantity,
    f.fill_price,
    -- Bonds quote per 100 of face, so notional = par * price / 100.
    round(f.fill_quantity * f.fill_price / 100.0, 2)       as fill_notional,
    o.order_created_at,
    f.filled_at,
    -- The core operational KPI input: seconds from order acceptance to this fill.
    extract(epoch from (f.filled_at - o.order_created_at)) as cycle_time_seconds
from fills f
join orders o on o.order_id = f.order_id
