package com.bonddesk.oms.fixedincome;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Holds the current US Treasury par-yield curve, the real risk-free benchmark that the
 * RFQ dealer engine prices bonds off. Fetches the live daily curve from the US Treasury
 * (keyless, public) and falls back to a hard-coded curve if the fetch fails or is disabled
 * (tests), so callers always have a usable curve.
 */
@Service
public class YieldCurveService {

    private static final Logger log = LoggerFactory.getLogger(YieldCurveService.class);
    private static final DateTimeFormatter TREASURY_DATE = DateTimeFormatter.ofPattern("MM/dd/yyyy");

    private final FixedIncomeProperties props;
    private final Clock clock;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).build();
    private final AtomicReference<YieldCurve> current;

    public YieldCurveService(FixedIncomeProperties props, Clock clock) {
        this.props = props;
        this.clock = clock;
        this.current = new AtomicReference<>(fallbackCurve());
    }

    public YieldCurve current() {
        return current.get();
    }

    @EventListener(ApplicationReadyEvent.class)
    public void loadOnStartup() {
        refresh();
    }

    @Scheduled(fixedDelayString = "${oms.fixedincome.curve-refresh-ms:21600000}", initialDelay = 21600000)
    public void refresh() {
        if (!props.isLiveCurve()) {
            log.info("Live Treasury curve disabled; using fallback curve as of {}", current().asOf());
            return;
        }
        try {
            YieldCurve fetched = fetchLive();
            current.set(fetched);
            log.info("Loaded live Treasury curve as of {} ({} tenors)", fetched.asOf(), fetched.tenors().length);
        } catch (RuntimeException e) {
            log.warn("Could not fetch live Treasury curve ({}); keeping {} curve as of {}",
                    e.getMessage(), current().source(), current().asOf());
        }
    }

    private YieldCurve fetchLive() {
        int year = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC).getYear();
        String url = props.getCurveCsvUrl().replace("{year}", String.valueOf(year));
        try {
            HttpResponse<String> res = http.send(
                    HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(10)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() / 100 != 2) {
                throw new IllegalStateException("HTTP " + res.statusCode());
            }
            return parseCsv(res.body());
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException(e.getMessage(), e);
        }
    }

    /** Parse the Treasury daily-rates CSV, taking the most recent row (first data line). */
    private YieldCurve parseCsv(String body) {
        String[] lines = body.split("\\r?\\n");
        if (lines.length < 2) {
            throw new IllegalStateException("empty curve CSV");
        }
        String[] header = splitCsv(lines[0]);
        String[] row = splitCsv(lines[1]);

        List<double[]> points = new ArrayList<>();
        for (int i = 1; i < header.length && i < row.length; i++) {
            Double tenor = tenorYears(header[i]);
            if (tenor == null || row[i].isBlank()) {
                continue;
            }
            try {
                points.add(new double[]{tenor, Double.parseDouble(row[i].trim())});
            } catch (NumberFormatException ignored) {
                // non-numeric cell — skip
            }
        }
        if (points.size() < 2) {
            throw new IllegalStateException("too few curve points parsed");
        }
        points.sort((a, b) -> Double.compare(a[0], b[0]));
        double[] tenors = new double[points.size()];
        double[] yields = new double[points.size()];
        for (int i = 0; i < points.size(); i++) {
            tenors[i] = points.get(i)[0];
            yields[i] = points.get(i)[1];
        }
        LocalDate asOf;
        try {
            asOf = LocalDate.parse(row[0].trim(), TREASURY_DATE);
        } catch (RuntimeException e) {
            asOf = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);
        }
        return new YieldCurve(asOf, tenors, yields, "US Treasury (live)");
    }

    private static String[] splitCsv(String line) {
        String[] parts = line.split(",");
        for (int i = 0; i < parts.length; i++) {
            parts[i] = parts[i].replace("\"", "").trim();
        }
        return parts;
    }

    /** Map a Treasury column header ("3 Mo", "10 Yr", ...) to a tenor in years. */
    private static Double tenorYears(String header) {
        return switch (header.toLowerCase().trim()) {
            case "1 mo" -> 1 / 12.0;
            case "1.5 month", "1.5 mo" -> 1.5 / 12.0;
            case "2 mo" -> 2 / 12.0;
            case "3 mo" -> 3 / 12.0;
            case "4 mo" -> 4 / 12.0;
            case "6 mo" -> 6 / 12.0;
            case "1 yr" -> 1.0;
            case "2 yr" -> 2.0;
            case "3 yr" -> 3.0;
            case "5 yr" -> 5.0;
            case "7 yr" -> 7.0;
            case "10 yr" -> 10.0;
            case "20 yr" -> 20.0;
            case "30 yr" -> 30.0;
            default -> null;
        };
    }

    /** A realistic recent curve used when the live fetch is unavailable. */
    private YieldCurve fallbackCurve() {
        double[] tenors = {1 / 12.0, 3 / 12.0, 6 / 12.0, 1, 2, 3, 5, 7, 10, 20, 30};
        double[] yields = {4.35, 4.32, 4.20, 4.00, 3.80, 3.75, 3.85, 4.00, 4.20, 4.55, 4.50};
        return new YieldCurve(LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC), tenors, yields, "fallback");
    }
}
