package com.bonddesk.risk;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Risk service — a small microservice that subscribes to the OMS's {@code order-events}
 * Kafka topic and maintains a live, in-memory view of desk risk (order counts by status
 * and filled notional per portfolio), exposed over REST. Demonstrates the event-driven,
 * loosely-coupled split: the OMS never calls this service; it only emits events.
 */
@SpringBootApplication
public class RiskApplication {

    public static void main(String[] args) {
        SpringApplication.run(RiskApplication.class, args);
    }
}
