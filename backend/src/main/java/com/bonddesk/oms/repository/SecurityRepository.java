package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Security;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SecurityRepository extends JpaRepository<Security, String> {

    List<Security> findByRestrictedFalse();

    List<Security> findBySectorIgnoreCase(String sector);

    List<Security> findByAssetClass(AssetClass assetClass);
}
