package com.bonddesk.oms.fixedincome.dto;

import com.bonddesk.oms.domain.Execution;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.fixedincome.DealerQuote;
import com.bonddesk.oms.fixedincome.Rfq;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** API view models for the fixed-income RFQ desk. */
public final class RfqDtos {

    private RfqDtos() {
    }

    public record CreateRfqRequest(
            @NotBlank(message = "cusip is required") String cusip,
            @NotBlank(message = "portfolio is required") String portfolio,
            @NotBlank(message = "trader is required") String trader,
            @NotNull(message = "side is required") OrderSide side,
            @NotNull(message = "quantity is required")
            @DecimalMin(value = "1000", message = "minimum RFQ size is 1,000 face") BigDecimal quantity
    ) {
    }

    public record RfqView(
            String id,
            String cusip,
            String description,
            OrderSide side,
            BigDecimal quantity,
            BigDecimal tenorYears,
            BigDecimal curveYieldPct,
            BigDecimal creditSpreadBps,
            BigDecimal fairYieldPct,
            BigDecimal fairClean,
            List<DealerQuote> quotes,
            String status,
            String acceptedDealer,
            String executedOrderRef,
            Instant createdAt,
            Instant expiresAt
    ) {
        public static RfqView from(Rfq r) {
            return new RfqView(
                    r.getId(), r.getCusip(), r.getDescription(), r.getSide(), r.getQuantity(),
                    r.getQuotes().tenorYears(), r.getQuotes().curveYieldPct(), r.getQuotes().creditSpreadBps(),
                    r.getQuotes().fairYieldPct(), r.getQuotes().fairClean(), r.getQuotes().quotes(),
                    r.getStatus().name(), r.getAcceptedDealer(), r.getExecutedOrderRef(),
                    r.getCreatedAt(), r.getExpiresAt());
        }
    }

    public record RfqExecutionView(
            String rfqId,
            String orderRef,
            String dealer,
            OrderSide side,
            BigDecimal quantity,
            BigDecimal price,
            String status
    ) {
        public static RfqExecutionView from(String rfqId, Order order) {
            List<Execution> execs = order.getExecutions();
            String dealer = execs.isEmpty() ? null : execs.get(execs.size() - 1).getVenue();
            return new RfqExecutionView(rfqId, order.getOrderRef(), dealer, order.getSide(),
                    order.getFilledQuantity(), order.getAvgFillPrice(), order.getStatus().name());
        }
    }
}
