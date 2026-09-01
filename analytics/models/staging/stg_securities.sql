-- Staging for OMS security reference data. Keyed by CUSIP.

with source as (
    select * from {{ source('oms', 'security') }}
)

select
    cusip,
    isin,
    description,
    issuer,
    sector,
    rating,
    coupon_rate,
    maturity_date,
    currency
from source
