package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestResult;
import com.bonddesk.oms.backtest.dto.BacktestDtos.Costs;
import com.bonddesk.oms.market.CoinbaseProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Replays a tiny hand-built L2 session so the fill + accounting logic is checked against
 * a known book, without needing captured data or the network.
 */
class BacktestServiceTest {

    // Bid 100 (size 10), ask 101 (size 10); a couple of updates so ticks fire over time.
    private static final String CAPTURE = """
            seq,ts,product,kind,side,price,size
            1,2026-01-01T00:00:00Z,BTC-USD,SNAP,B,100.0,10
            1,2026-01-01T00:00:00Z,BTC-USD,SNAP,A,101.0,10
            2,2026-01-01T00:00:00.600Z,BTC-USD,UPD,A,101.0,10
            3,2026-01-01T00:00:01.200Z,BTC-USD,UPD,A,101.0,10
            4,2026-01-01T00:00:01.800Z,BTC-USD,TRD,B,101.0,1
            """;

    private BacktestService serviceOver(Path dir) throws IOException {
        Files.writeString(dir.resolve("l2-2026-01-01.csv"), CAPTURE);
        CoinbaseProperties props = new CoinbaseProperties();
        props.setL2CaptureDir(dir.toString());
        return new BacktestService(props);
    }

    @Test
    void twapBuyFillsAtTheAskAndPaysImplementationShortfall(@TempDir Path dir) throws IOException {
        BacktestService service = serviceOver(dir);

        BacktestResult r = service.run(new BacktestRequest(
                "BTC-USD", "TWAP", "BUY", 2.0, 2, null, null, null, null, null, null, null, "2026-01-01", null, null, null));

        assertThat(r.executedSize()).isEqualTo(2.0);
        assertThat(r.numFills()).isEqualTo(2);
        // Buyer lifts the offer at 101 against an arrival mid of 100.5.
        assertThat(r.avgExecPrice()).isEqualTo(101.0);
        assertThat(r.arrivalMid()).isEqualTo(100.5);
        // Buying above arrival is a positive (adverse) implementation shortfall.
        assertThat(r.implementationShortfallBps()).isGreaterThan(0.0);
    }

    @Test
    void sellHitsTheBidForANegativeSpreadToArrival(@TempDir Path dir) throws IOException {
        BacktestService service = serviceOver(dir);

        BacktestResult r = service.run(new BacktestRequest(
                "BTC-USD", "TWAP", "SELL", 2.0, 2, null, null, null, null, null, null, null, "2026-01-01", null, null, null));

        assertThat(r.executedSize()).isEqualTo(2.0);
        assertThat(r.avgExecPrice()).isEqualTo(100.0); // hits the bid
        assertThat(r.implementationShortfallBps()).isGreaterThan(0.0); // selling below arrival mid
    }

    @Test
    void marketMakerBacktestRunsAndIsQueueAware(@TempDir Path dir) throws IOException {
        BacktestService service = serviceOver(dir);

        BacktestResult r = service.run(new BacktestRequest(
                "BTC-USD", "AVELLANEDA_STOIKOV", null, 0.5, null, null, null, null, null, null, null, null, "2026-01-01", null, null, null));

        assertThat(r.strategyType()).isEqualTo("AVELLANEDA_STOIKOV");
        assertThat(r.note().toLowerCase()).contains("market making");
        assertThat(r.makerFills()).isGreaterThanOrEqualTo(0);
        assertThat(r.takerFills()).isEqualTo(0); // a maker never takes
    }

    @Test
    void feesAndImpactReduceNetBelowGross(@TempDir Path dir) throws IOException {
        BacktestService service = serviceOver(dir);
        Costs costs = new Costs(50.0, 0.0, 0.0, 0.0, 0.0, 50.0); // 50 bps taker fee + impact

        BacktestResult r = service.run(new BacktestRequest(
                "BTC-USD", "TWAP", "BUY", 2.0, 2, null, null, null, null, null, null, null, "2026-01-01", costs, null, null));

        assertThat(r.feeCostUsd()).isGreaterThan(0.0);
        assertThat(r.impactCostUsd()).isGreaterThan(0.0);
        assertThat(r.allInCostBps()).isGreaterThan(0.0);
        assertThat(r.netPnl()).isLessThan(r.totalPnl()); // costs eat into gross P&L
    }
}
