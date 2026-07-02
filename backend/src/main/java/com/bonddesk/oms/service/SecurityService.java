package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.repository.SecurityRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/** Read access to the bond reference-data (security master). */
@Service
public class SecurityService {

    private final SecurityRepository securities;

    public SecurityService(SecurityRepository securities) {
        this.securities = securities;
    }

    @Transactional(readOnly = true)
    public List<Security> list(String sector) {
        return (sector == null || sector.isBlank())
                ? securities.findAll()
                : securities.findBySectorIgnoreCase(sector);
    }

    @Transactional(readOnly = true)
    public Security get(String cusip) {
        return securities.findById(cusip)
                .orElseThrow(() -> new NotFoundException("No security with cusip " + cusip));
    }
}
