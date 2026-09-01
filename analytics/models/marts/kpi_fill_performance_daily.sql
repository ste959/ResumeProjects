-- kpi_fill_performance_daily — the standardized daily operational KPIs a desk lead or exec
-- reviews: throughput (orders, fills), quality (fill rate, reject rate), and speed (order-to-fill
-- cycle-time percentiles). Grain: one row per trade date. This is the model BI dashboards point at.

with orders as (
    select * from {{ ref('stg_orders') }}
),

fills as (
    select * from {{ ref('fct_fills') }}
),

orders_by_day as (
    select
        date_trunc('day', order_created_at)::date          as trade_date,
        count(*)                                            as orders_submitted,
        count(*) filter (where status = 'FILLED')           as orders_filled,
        count(*) filter (where status = 'PARTIALLY_FILLED') as orders_partially_filled,
        count(*) filter (where status = 'REJECTED')         as orders_rejected,
        count(*) filter (where status = 'CANCELLED')        as orders_cancelled
    from orders
    group by 1
),

fills_by_day as (
    select
        date_trunc('day', filled_at)::date                                     as trade_date,
        count(*)                                                               as fills,
        round(avg(cycle_time_seconds)::numeric, 3)                             as cycle_time_avg_s,
        round(percentile_cont(0.5) within group (order by cycle_time_seconds)::numeric, 3)  as cycle_time_p50_s,
        round(percentile_cont(0.95) within group (order by cycle_time_seconds)::numeric, 3) as cycle_time_p95_s
    from fills
    group by 1
)

select
    o.trade_date,
    o.orders_submitted,
    o.orders_filled,
    o.orders_partially_filled,
    o.orders_rejected,
    o.orders_cancelled,
    -- Fill rate and reject rate as fractions of submitted orders; nullif guards a zero-order day.
    round(o.orders_filled::numeric   / nullif(o.orders_submitted, 0), 4) as fill_rate,
    round(o.orders_rejected::numeric / nullif(o.orders_submitted, 0), 4) as reject_rate,
    coalesce(f.fills, 0)                                                 as fills,
    f.cycle_time_avg_s,
    f.cycle_time_p50_s,
    f.cycle_time_p95_s
from orders_by_day o
left join fills_by_day f on f.trade_date = o.trade_date
order by o.trade_date
