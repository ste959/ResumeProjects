-- Indexes for the hot read patterns found in the audit.

-- The blotter lists orders filtered by status or portfolio and sorted by created_at DESC. Composite
-- indexes serve both the filter and the sort (no scan + in-memory sort). These subsume the old
-- single-column status/portfolio indexes, so drop those to avoid redundant indexes.
DROP INDEX IF EXISTS idx_orders_status;
DROP INDEX IF EXISTS idx_orders_portfolio;
CREATE INDEX idx_orders_status_created    ON orders (status, created_at DESC);
CREATE INDEX idx_orders_portfolio_created ON orders (portfolio, created_at DESC);
CREATE INDEX idx_orders_created           ON orders (created_at DESC);   -- unfiltered blotter sort

-- LiquidityProvider polls restricted=false every ~1.5s.
CREATE INDEX idx_security_restricted ON security (restricted);
