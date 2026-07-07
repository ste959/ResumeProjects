package com.bonddesk.oms.rebalance;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Verifies the Jackson mapping of the target-book JSON, including that unknown properties
 * (e.g. the research {@code note}) are ignored.
 */
class TargetBookLoaderTest {

    private final TargetBookLoader loader = new TargetBookLoader(new ObjectMapper(), new RebalanceProperties());

    @Test
    void parsesTargetBookAndIgnoresUnknownProperties() {
        String json = """
                {
                  "asOf": "2026-07-02",
                  "strategy": "neutralized_momentum",
                  "note": "PLUMBING TEST ONLY",
                  "grossLong": 0.5,
                  "grossShort": -0.5,
                  "names": [
                    {"symbol": "AAPL", "weight": 0.006895, "price": 308.235, "extra": 1},
                    {"symbol": "ABT", "weight": -0.01689, "price": 95.28}
                  ]
                }
                """;

        TargetBook book = loader.parse(json);

        assertThat(book.asOf()).isEqualTo("2026-07-02");
        assertThat(book.strategy()).isEqualTo("neutralized_momentum");
        assertThat(book.grossLong()).isEqualByComparingTo("0.5");
        assertThat(book.grossShort()).isEqualByComparingTo("-0.5");
        assertThat(book.names()).hasSize(2);

        TargetWeight aapl = book.names().get(0);
        assertThat(aapl.symbol()).isEqualTo("AAPL");
        assertThat(aapl.weight()).isEqualByComparingTo("0.006895");
        assertThat(aapl.price()).isEqualByComparingTo("308.235");

        TargetWeight abt = book.names().get(1);
        assertThat(abt.symbol()).isEqualTo("ABT");
        assertThat(abt.weight()).isEqualByComparingTo(new BigDecimal("-0.01689"));
    }
}
