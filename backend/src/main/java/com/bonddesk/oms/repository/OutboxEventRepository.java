package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.OutboxEvent;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;

public interface OutboxEventRepository extends JpaRepository<OutboxEvent, Long> {

    /** The oldest still-unpublished, non-dead-lettered rows, in order, capped for a bounded relay batch.
     *  Excluding dead-lettered rows is what lets the relay skip a poison row instead of re-fetching it. */
    List<OutboxEvent> findByPublishedAtIsNullAndDeadLetteredAtIsNullOrderByIdAsc(Limit limit);

    /** Bulk-delete published rows older than the cutoff — the retention purge that bounds table growth. */
    @Modifying
    @Query("DELETE FROM OutboxEvent o WHERE o.publishedAt IS NOT NULL AND o.publishedAt < :cutoff")
    int deletePublishedBefore(@Param("cutoff") Instant cutoff);

    /** Dead-lettered rows, for observability / a manual replay tool. */
    long countByDeadLetteredAtIsNotNull();
}
