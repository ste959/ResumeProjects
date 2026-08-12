package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.OutboxEvent;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OutboxEventRepository extends JpaRepository<OutboxEvent, Long> {

    /** The oldest still-unpublished rows, in insertion order, capped for a bounded relay batch. */
    List<OutboxEvent> findByPublishedAtIsNullOrderByIdAsc(Limit limit);
}
