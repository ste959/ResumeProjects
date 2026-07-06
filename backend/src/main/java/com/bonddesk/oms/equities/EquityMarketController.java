package com.bonddesk.oms.equities;

import com.bonddesk.oms.equities.AlpacaBrokerClient.AccountInfo;
import com.bonddesk.oms.equities.dto.EquityDtos.AccountView;
import com.bonddesk.oms.equities.dto.EquityDtos.EquityQuoteView;
import com.bonddesk.oms.equities.dto.EquityDtos.EquityTradeView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/** Live equity market data (Alpaca IEX feed) and paper-account summary. */
@RestController
@RequestMapping("/api/equities")
@Tag(name = "Equities", description = "Live equity market data and paper-broker account (Alpaca)")
public class EquityMarketController {

    private static final BigDecimal BPS = BigDecimal.valueOf(10_000);

    private final EquityMarketDataService marketData;
    private final AlpacaBrokerClient broker;

    public EquityMarketController(EquityMarketDataService marketData, AlpacaBrokerClient broker) {
        this.marketData = marketData;
        this.broker = broker;
    }

    @GetMapping("/quotes")
    @Operation(summary = "Top-of-book quotes for all streamed equities")
    public List<EquityQuoteView> quotes() {
        return marketData.allQuotes().stream().map(this::view).toList();
    }

    @GetMapping("/{symbol}/trades")
    @Operation(summary = "Recent trade prints for an equity")
    public List<EquityTradeView> trades(@PathVariable String symbol) {
        return marketData.recentTrades(symbol).stream()
                .map(t -> new EquityTradeView(t.seq(), t.symbol(), t.price(), t.size(), t.time()))
                .toList();
    }

    @GetMapping("/account")
    @Operation(summary = "Alpaca paper-trading account summary")
    public AccountView account() {
        AccountInfo a = broker.account();
        if (a == null) {
            return new AccountView("DISCONNECTED", null, null, null, "USD", false);
        }
        return new AccountView(a.status(), a.cash(), a.buyingPower(), a.equity(), a.currency(), true);
    }

    private EquityQuoteView view(EquityQuote q) {
        BigDecimal bid = q.bid();
        BigDecimal ask = q.ask();
        boolean twoSided = bid != null && ask != null && bid.signum() > 0 && ask.signum() > 0;
        BigDecimal mid = twoSided ? bid.add(ask).divide(BigDecimal.valueOf(2), 4, RoundingMode.HALF_UP) : null;
        BigDecimal spread = twoSided ? ask.subtract(bid) : null;
        BigDecimal spreadBps = (mid != null && mid.signum() > 0)
                ? spread.multiply(BPS).divide(mid, 2, RoundingMode.HALF_UP) : null;
        return new EquityQuoteView(q.symbol(), bid, ask, mid, spread, spreadBps,
                q.bidSize(), q.askSize(), q.last());
    }
}
