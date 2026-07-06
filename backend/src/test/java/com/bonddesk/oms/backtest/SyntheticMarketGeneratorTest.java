package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestResult;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticResult;
import com.bonddesk.oms.market.CoinbaseProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class SyntheticMarketGeneratorTest {

    @Test
    void generatesAReplayableSessionTheEngineCanConsume(@TempDir Path dir) {
        CoinbaseProperties props = new CoinbaseProperties();
        props.setL2CaptureDir(dir.toString());

        SyntheticResult gen = new SyntheticMarketGenerator(props).generate(new SyntheticRequest(
                "sig", 60, 250L, 100.0, 5.0, 0.0, 4.0, 5, 5.0, 1, 2.0, 7L));

        assertThat(gen.events()).isGreaterThan(0);
        assertThat(gen.ticks()).isGreaterThan(0);
        assertThat(gen.injectedAlpha()).isEqualTo(2.0);
        assertThat(Files.exists(dir.resolve("l2-sig.csv"))).isTrue();

        // The same replay engine consumes the synthetic session as any recorded one.
        BacktestResult bt = new BacktestService(props).run(new BacktestRequest(
                "SYNTH-USD", "TWAP", "BUY", 1.0, 5, null, null, null, null, null,
                null, null, "sig", null, null, null));
        assertThat(bt.executedSize()).isGreaterThan(0.0);
    }
}
