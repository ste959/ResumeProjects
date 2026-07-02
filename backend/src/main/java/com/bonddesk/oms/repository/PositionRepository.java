package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.Position;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface PositionRepository extends JpaRepository<Position, Long> {

    Optional<Position> findByPortfolioAndSecurity_Cusip(String portfolio, String cusip);

    List<Position> findByPortfolioOrderBySecurity_Cusip(String portfolio);
}
