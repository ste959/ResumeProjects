-- dim_security — the security dimension. One row per CUSIP; the conformed key (security_key)
-- joins to fct_fills so BI can slice execution metrics by sector, rating, or issuer.

select
    cusip as security_key,
    cusip,
    isin,
    description,
    issuer,
    sector,
    rating,
    coupon_rate,
    maturity_date,
    currency
from {{ ref('stg_securities') }}
