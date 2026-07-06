package com.bonddesk.oms.market;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import jakarta.annotation.PreDestroy;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;

/**
 * Captures a per-second microstructure snapshot of each product's top of book to a CSV,
 * turning the ephemeral live feed into a research dataset the Python layer can backtest
 * over. Records mid, microprice, top-of-book sizes, spread and order-book imbalance —
 * the raw material for microstructure signals.
 */
@Component
@ConditionalOnProperty(prefix = "oms.crypto", name = "recorder-enabled", havingValue = "true", matchIfMissing = true)
public class MarketRecorder {

    private static final Logger log = LoggerFactory.getLogger(MarketRecorder.class);
    private static final String HEADER =
            "ts,product,bid,ask,mid,microprice,bid_size,ask_size,spread,imbalance\n";

    private final CoinbaseProperties props;
    private final MarketDataService marketData;
    private final Clock clock;
    private BufferedWriter writer;
    private LocalDate openFor;

    public MarketRecorder(CoinbaseProperties props, MarketDataService marketData, Clock clock) {
        this.props = props;
        this.marketData = marketData;
        this.clock = clock;
    }

    @Scheduled(fixedDelay = 1000)
    public void snapshot() {
        for (String product : marketData.products()) {
            LiveOrderBook book = marketData.book(product);
            if (!book.isReady()) {
                continue;
            }
            try {
                writeRow(product, book);
            } catch (IOException e) {
                log.debug("Recorder write failed: {}", e.getMessage());
            }
        }
    }

    private synchronized void writeRow(String product, LiveOrderBook book) throws IOException {
        rollFileIfNeeded();
        BigDecimal bid = book.bestBid(), ask = book.bestAsk();
        BigDecimal bs = book.bestBidSize(), as = book.bestAskSize();
        BigDecimal spread = ask.subtract(bid);
        BigDecimal imbalance = bs.subtract(as).divide(bs.add(as), 6, java.math.RoundingMode.HALF_UP);
        writer.write(clock.instant() + "," + product + "," + bid + "," + ask + "," + book.mid()
                + "," + book.microprice() + "," + bs + "," + as + "," + spread + "," + imbalance + "\n");
        writer.flush();
    }

    private void rollFileIfNeeded() throws IOException {
        LocalDate today = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);
        if (writer != null && today.equals(openFor)) {
            return;
        }
        close();
        Path dir = Path.of(props.getRecorderDir());
        Files.createDirectories(dir);
        Path file = dir.resolve("quotes-" + today + ".csv");
        boolean fresh = !Files.exists(file);
        writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        if (fresh) {
            writer.write(HEADER);
        }
        openFor = today;
        log.info("Recording market data to {}", file.toAbsolutePath());
    }

    @PreDestroy
    public synchronized void close() {
        if (writer != null) {
            try {
                writer.close();
            } catch (IOException ignored) {
                // best effort
            }
            writer = null;
        }
    }
}
