-- Data-quality: a reconciliation check between the two operational tables. Every recorded fill
-- must roll up to its order's filled_quantity, and fills must never exceed the ordered quantity.
-- (The trading analogue of "received quantity must reconcile to the purchase order.") dbt fails
-- the build if this query returns any rows.

with fills_per_order as (
    select
        order_id,
        sum(fill_quantity) as total_filled
    from {{ ref('stg_executions') }}
    group by order_id
),

orders as (
    select * from {{ ref('stg_orders') }}
)

select
    o.order_id,
    o.order_ref,
    o.ordered_quantity,
    o.filled_quantity,
    r.total_filled
from orders o
join fills_per_order r on r.order_id = o.order_id
where abs(o.filled_quantity - r.total_filled) > 0.005   -- fills must reconcile to filled_quantity
   or r.total_filled > o.ordered_quantity + 0.005       -- and must never overfill the order
