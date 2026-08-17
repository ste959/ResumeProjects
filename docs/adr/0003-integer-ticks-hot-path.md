# 3. Integer ticks/lots on the matching hot path (no BigDecimal)

**Status:** Accepted

## Context
Prices and quantities are money, and money in Java usually means `BigDecimal` for correctness. But the
matching engine compares prices and sizes millions of times per second, and `BigDecimal` compares
allocate and are slow.

## Decision
Represent prices as `long` **integer ticks** and sizes as `long` **lots** inside the engine. Conversion
to/from `BigDecimal` happens at the boundary (order entry / persistence), never in the match loop. The
engine core knows nothing about `BigDecimal` or JPA.

## Consequences
- **Gain:** allocation-free, branch-predictable comparisons; deterministic integer arithmetic; the
  benchmark (~3M ord/s) reflects real engine cost, not boxing.
- **Cost:** a tick/lot scale must be defined per instrument, and boundary conversions must be correct
  (tested).
- **Alternative rejected:** `BigDecimal` end-to-end — correct but too slow and allocation-heavy for the
  hot path, and it would make the benchmark meaningless.
