package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderRef(String orderRef);

    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    List<Order> findByPortfolioOrderByCreatedAtDesc(String portfolio);

    List<Order> findAllByOrderByCreatedAtDesc();

    /** Working orders the execution simulator may fill. */
    List<Order> findByStatusInOrderByCreatedAtAsc(List<OrderStatus> statuses);
}
