-- Schema evolution for the reporting layer: indexes that support the analytical query
-- patterns, plus a view that encapsulates the transaction-cost-analysis query so BI
-- tools and analysts can read it directly (the application issues the equivalent SQL
-- via JdbcTemplate to stay portable across PostgreSQL and H2).

-- Foreign-key columns are not auto-indexed in PostgreSQL; these support the joins and
-- the daily-volume roll-up.
CREATE INDEX idx_orders_cusip ON orders (cusip);
CREATE INDEX idx_execution_executed_at ON execution (executed_at);

-- Execution-quality (TCA) reporting view.
CREATE VIEW v_execution_quality AS
SELECT s.cusip                                     AS cusip,
       s.description                               AS description,
       o.side                                      AS side,
       COUNT(DISTINCT o.id)                        AS order_count,
       SUM(e.quantity)                             AS filled_face,
       SUM(e.quantity * e.price) / SUM(e.quantity) AS avg_fill_price,
       s.clean_price                               AS benchmark_price
FROM execution e
JOIN orders o   ON o.id = e.order_id
JOIN security s ON s.cusip = o.cusip
GROUP BY s.cusip, s.description, o.side, s.clean_price;
