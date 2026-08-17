package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderRef(String orderRef);

    /**
     * One keyset page of the blotter, newest first. Optional {@code status}/{@code portfolio} filters and
     * a keyset predicate on {@code (createdAt, id)} — everything strictly before the cursor — are all
     * served by the composite indexes in V6 ({@code (status, created_at)}, {@code (portfolio, created_at)},
     * {@code (created_at)}). The {@code security} to-one is join-fetched (safe with a limit); the
     * {@code executions} collection is deliberately not fetched, so the {@code Pageable} limit is a real
     * SQL {@code LIMIT} rather than an in-memory slice. Pass a {@code Pageable} with no sort — the query
     * owns the ordering.
     */
    @Query("""
            SELECT o FROM Order o
            JOIN FETCH o.security
            WHERE (:status IS NULL OR o.status = :status)
              AND (:portfolio IS NULL OR o.portfolio = :portfolio)
              AND (:cursorCreatedAt IS NULL
                   OR o.createdAt < :cursorCreatedAt
                   OR (o.createdAt = :cursorCreatedAt AND o.id < :cursorId))
            ORDER BY o.createdAt DESC, o.id DESC
            """)
    List<Order> findBlotterPage(@Param("status") OrderStatus status,
                                @Param("portfolio") String portfolio,
                                @Param("cursorCreatedAt") Instant cursorCreatedAt,
                                @Param("cursorId") Long cursorId,
                                Pageable pageable);

    /** Working orders the execution simulator may fill. */
    List<Order> findByStatusInOrderByCreatedAtAsc(List<OrderStatus> statuses);
}
