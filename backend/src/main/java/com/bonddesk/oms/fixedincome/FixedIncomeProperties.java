package com.bonddesk.oms.fixedincome;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuration for the fixed-income RFQ desk: whether to pull the live US Treasury yield
 * curve, how many dealers respond to a quote request, and how long quotes stay firm.
 */
@ConfigurationProperties(prefix = "oms.fixedincome")
public class FixedIncomeProperties {

    /** When true, fetch the real daily Treasury par-yield curve; else use the fallback. */
    private boolean liveCurve = true;

    /** US Treasury daily par-yield CSV endpoint; {year} is substituted at fetch time. */
    private String curveCsvUrl = "https://home.treasury.gov/resource-center/data-chart-center/"
            + "interest-rates/daily-treasury-rates.csv/{year}/all"
            + "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv";

    /** How often to refresh the curve, in milliseconds (default 6 hours). */
    private long curveRefreshMs = 6 * 60 * 60 * 1000L;

    /** Number of dealers that respond to an RFQ. */
    private int dealerCount = 5;

    /** How long dealer quotes stay firm before the RFQ expires, in seconds. */
    private int rfqTtlSeconds = 30;

    public boolean isLiveCurve() {
        return liveCurve;
    }

    public void setLiveCurve(boolean liveCurve) {
        this.liveCurve = liveCurve;
    }

    public String getCurveCsvUrl() {
        return curveCsvUrl;
    }

    public void setCurveCsvUrl(String curveCsvUrl) {
        this.curveCsvUrl = curveCsvUrl;
    }

    public long getCurveRefreshMs() {
        return curveRefreshMs;
    }

    public void setCurveRefreshMs(long curveRefreshMs) {
        this.curveRefreshMs = curveRefreshMs;
    }

    public int getDealerCount() {
        return dealerCount;
    }

    public void setDealerCount(int dealerCount) {
        this.dealerCount = dealerCount;
    }

    public int getRfqTtlSeconds() {
        return rfqTtlSeconds;
    }

    public void setRfqTtlSeconds(int rfqTtlSeconds) {
        this.rfqTtlSeconds = rfqTtlSeconds;
    }
}
