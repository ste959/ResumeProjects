# 2. Two order-book implementations, kept on purpose

**Status:** Accepted

## Context
The repo has two classes named `OrderBook`: `com.bonddesk.exchange.OrderBook` and
`com.bonddesk.oms.matching.OrderBook`. On first read this looks like duplication or dead code.

## Decision
Keep both, and document the division of labor in each class Javadoc (and `backend/README.md`):
- **`exchange.OrderBook`** is the standalone **reference engine** — integer ticks, allocation-light hot
  path, full exchange semantics (IOC/FOK/post-only/STP/replace, L2/L3), JMH-benchmarked. It has no
  persistence or Spring dependencies, which is exactly what lets it be benchmarked in isolation.
- **`oms.matching.OrderBook`** is the **OMS-integrated crosser** for BigDecimal-priced desk orders,
  wired through `MatchingService` into the JPA order/fill lifecycle.

## Consequences
- **Gain:** the performance-critical engine stays free of the JPA/BigDecimal weight it would otherwise
  carry; each serves its context cleanly.
- **Cost:** two implementations of a similar structure to keep correct (both are tested, incl. jqwik
  property tests on the exchange engine).
- **Alternative rejected:** one shared engine parameterized over price type and persistence — it would
  drag persistence concerns into the hot path and make the benchmark unrepresentative.
