package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.repository.SecurityRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/** Read access to the multi-asset reference-data (security master). */
@Service
public class SecurityService {

    private final SecurityRepository securities;

    public SecurityService(SecurityRepository securities) {
        this.securities = securities;
    }

    /**
     * List securities, optionally narrowed by asset class and/or sector. Both filters are
     * optional; when both are supplied they are combined (asset class then sector).
     */
    @Transactional(readOnly = true)
    public List<Security> list(String sector, AssetClass assetClass) {
        List<Security> base = (assetClass == null)
                ? securities.findAll()
                : securities.findByAssetClass(assetClass);
        if (sector == null || sector.isBlank()) {
            return base;
        }
        return base.stream()
                .filter(s -> sector.equalsIgnoreCase(s.getSector()))
                .toList();
    }

    @Transactional(readOnly = true)
    public Security get(String cusip) {
        return securities.findById(cusip)
                .orElseThrow(() -> new NotFoundException("No security with cusip " + cusip));
    }
}
