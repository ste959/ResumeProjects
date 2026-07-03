package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.repository.SecurityRepository;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;

/**
 * A simple automated market-maker that keeps a two-sided book in every tradable security,
 * so the desk always has a real market to trade against. On each tick it random-walks the
 * mid, cancels its prior quotes, and re-posts several levels of depth on each side.
 *
 * <p>This <em>replaces</em> the old random fill simulator: fills are now the result of
 * genuine price-time-priority matching against this resting liquidity, not a coin flip.
 */
@Component
@ConditionalOnProperty(prefix = "oms.matching", name = "enabled", havingValue = "true")
public class LiquidityProvider {

    private static final int LEVELS = 3;
    private static final long LEVEL_STEP_TICKS = 250;  // 0.025 pt between levels
    private static final long HALF_SPREAD_TICKS = 250; // 0.025 pt half-spread
    private static final long SIZE = 2_000_000;        // face per level
    private static final int MAX_WALK_TICKS = 6;       // mid drift per tick

    private final SecurityRepository securities;
    private final MatchingService matching;
    private final Map<String, Long> mid = new ConcurrentHashMap<>();
    private final Map<String, List<Long>> quotes = new ConcurrentHashMap<>();

    public LiquidityProvider(SecurityRepository securities, MatchingService matching) {
        this.securities = securities;
        this.matching = matching;
    }

    @Scheduled(fixedDelayString = "${oms.matching.liquidity.interval-ms:1500}")
    public void refresh() {
        for (Security s : securities.findByRestrictedFalse()) {
            refreshQuotesFor(s);
        }
    }

    private void refreshQuotesFor(Security s) {
        String cusip = s.getCusip();
        long m = mid.computeIfAbsent(cusip, k -> Ticks.priceToTicks(s.getCleanPrice()));
        m += ThreadLocalRandom.current().nextInt(-MAX_WALK_TICKS, MAX_WALK_TICKS + 1); // random walk
        mid.put(cusip, m);

        // Pull existing quotes before re-posting so resting liquidity stays bounded.
        List<Long> previous = quotes.remove(cusip);
        if (previous != null) {
            previous.forEach(id -> matching.cancelLiquidity(cusip, id));
        }

        List<Long> posted = new ArrayList<>(LEVELS * 2);
        for (int i = 0; i < LEVELS; i++) {
            long bid = m - HALF_SPREAD_TICKS - (long) i * LEVEL_STEP_TICKS;
            long ask = m + HALF_SPREAD_TICKS + (long) i * LEVEL_STEP_TICKS;
            posted.add(matching.postLiquidity(cusip, OrderSide.BUY, bid, SIZE));
            posted.add(matching.postLiquidity(cusip, OrderSide.SELL, ask, SIZE));
        }
        quotes.put(cusip, posted);
    }
}
