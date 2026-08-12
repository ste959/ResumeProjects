package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderRef(String orderRef);

    // The blotter needs each order's security and executions. Fetch them in one query via an entity
    // graph so a full blotter is a single SELECT, not 2N+1 (one lazy fill query per row + the EAGER
    // security join per row). Collections dedupe entities; these methods aren't paginated.
    @EntityGraph(attributePaths = {"security", "executions"})
    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    @EntityGraph(attributePaths = {"security", "executions"})
    List<Order> findByPortfolioOrderByCreatedAtDesc(String portfolio);

    @EntityGraph(attributePaths = {"security", "executions"})
    List<Order> findAllByOrderByCreatedAtDesc();

    /** Working orders the execution simulator may fill. */
    List<Order> findByStatusInOrderByCreatedAtAsc(List<OrderStatus> statuses);
}
