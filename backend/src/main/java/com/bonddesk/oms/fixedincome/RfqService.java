package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.fixedincome.dto.RfqDtos.CreateRfqRequest;
import com.bonddesk.oms.repository.SecurityRepository;
import com.bonddesk.oms.service.OrderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * Orchestrates the request-for-quote workflow: build a bond RFQ, collect firm dealer
 * quotes off the real curve, and — on acceptance — book the trade at the chosen dealer's
 * price through the standard order/compliance/position path. RFQs live in memory (they
 * expire in seconds); the executed trade is persisted like any other.
 */
@Service
public class RfqService {

    private static final Logger log = LoggerFactory.getLogger(RfqService.class);
    private static final int MAX_RFQS = 50;

    private final SecurityRepository securities;
    private final DealerQuoteEngine engine;
    private final OrderService orders;
    private final FixedIncomeProperties props;
    private final Clock clock;

    private final Map<String, Rfq> rfqs = new ConcurrentHashMap<>();
    private final Deque<String> order = new ConcurrentLinkedDeque<>();

    public RfqService(SecurityRepository securities, DealerQuoteEngine engine, OrderService orders,
                      FixedIncomeProperties props, Clock clock) {
        this.securities = securities;
        this.engine = engine;
        this.orders = orders;
        this.props = props;
        this.clock = clock;
    }

    public Rfq create(CreateRfqRequest req) {
        Security security = securities.findById(req.cusip())
                .orElseThrow(() -> new NotFoundException("No security with cusip " + req.cusip()));
        if (security.getAssetClass() != AssetClass.FIXED_INCOME) {
            throw new BadRequestException("RFQ is for fixed income only; " + req.cusip()
                    + " is " + security.getAssetClass());
        }

        String id = UUID.randomUUID().toString();
        QuoteSet quotes = engine.quote(security, req.side(), req.quantity(), new Random(id.hashCode()));
        Instant now = clock.instant();
        Rfq rfq = new Rfq(id, security.getCusip(), security.getDescription(), req.portfolio(), req.trader(),
                req.side(), req.quantity(), quotes, now, now.plusSeconds(props.getRfqTtlSeconds()));

        rfqs.put(id, rfq);
        order.addFirst(id);
        trim();
        log.info("RFQ {} created: {} {} {} — {} dealer quotes, best {}", id, req.side(), req.quantity(),
                security.getCusip(), quotes.quotes().size(), bestDealer(rfq));
        return rfq;
    }

    public Rfq get(String id) {
        Rfq rfq = rfqs.get(id);
        if (rfq == null) {
            throw new NotFoundException("No RFQ with id " + id);
        }
        expireIfNeeded(rfq);
        return rfq;
    }

    public List<Rfq> list() {
        List<Rfq> out = new ArrayList<>();
        for (String id : order) {
            Rfq rfq = rfqs.get(id);
            if (rfq != null) {
                expireIfNeeded(rfq);
                out.add(rfq);
            }
        }
        return out;
    }

    /**
     * Accept a quote and book the trade. If {@code dealer} is null the best execution is
     * taken; otherwise the named dealer's quote is used (e.g. to trade away from best).
     */
    public Order accept(String id, String dealer) {
        Rfq rfq = get(id);
        if (rfq.getStatus() == RfqStatus.EXECUTED) {
            throw new BadRequestException("RFQ " + id + " has already been executed");
        }
        if (rfq.getStatus() == RfqStatus.EXPIRED) {
            throw new BadRequestException("RFQ " + id + " has expired; request a new quote");
        }

        DealerQuote quote = pickQuote(rfq, dealer);
        Order filled = orders.executeRfqFill(rfq.getCusip(), rfq.getPortfolio(), rfq.getTrader(),
                rfq.getSide(), rfq.getQuantity(), quote.price(), quote.dealer());

        rfq.setStatus(RfqStatus.EXECUTED);
        rfq.setAcceptedDealer(quote.dealer());
        rfq.setExecutedOrderRef(filled.getOrderRef());
        log.info("RFQ {} executed with {} @ {} -> order {}", id, quote.dealer(), quote.price(),
                filled.getOrderRef());
        return filled;
    }

    private DealerQuote pickQuote(Rfq rfq, String dealer) {
        List<DealerQuote> quotes = rfq.getQuotes().quotes();
        if (dealer == null || dealer.isBlank()) {
            return quotes.stream().filter(DealerQuote::best).findFirst()
                    .orElseThrow(() -> new BadRequestException("RFQ has no quotes"));
        }
        return quotes.stream().filter(q -> q.dealer().equalsIgnoreCase(dealer)).findFirst()
                .orElseThrow(() -> new BadRequestException("No quote from dealer " + dealer));
    }

    private void expireIfNeeded(Rfq rfq) {
        if (rfq.getStatus() == RfqStatus.QUOTED && rfq.isExpired(clock.instant())) {
            rfq.setStatus(RfqStatus.EXPIRED);
        }
    }

    private String bestDealer(Rfq rfq) {
        return rfq.getQuotes().quotes().stream().filter(DealerQuote::best).findFirst()
                .map(DealerQuote::dealer).orElse("—");
    }

    private void trim() {
        while (order.size() > MAX_RFQS) {
            String evict = order.pollLast();
            if (evict != null) {
                rfqs.remove(evict);
            }
        }
    }
}
