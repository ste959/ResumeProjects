package com.bonddesk.oms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * BondDesk OMS — a Fixed Income Order &amp; Execution Management System.
 *
 * <p>Models the core trading workflow of a fixed-income desk: a trader stages a bond
 * order, it is checked against compliance rules, routed to an execution venue, and
 * filled (fully or partially). Fills update the firm's positions in near real time.
 */
@EnableScheduling
@SpringBootApplication
public class OmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OmsApplication.class, args);
    }
}
