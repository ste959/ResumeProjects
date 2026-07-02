package com.bonddesk.oms.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Landing endpoint so hitting the API root returns useful pointers rather than a 404. */
@RestController
@Tag(name = "Info", description = "Service metadata")
public class HomeController {

    @GetMapping("/")
    @Operation(summary = "Service info and useful links")
    public Map<String, Object> home() {
        return Map.of(
                "service", "BondDesk OMS",
                "description", "Fixed Income Order & Execution Management System",
                "version", "1.0.0",
                "links", Map.of(
                        "apiDocs", "/swagger-ui.html",
                        "openApiSpec", "/v3/api-docs",
                        "health", "/actuator/health",
                        "securities", "/api/securities",
                        "orders", "/api/orders"
                )
        );
    }
}
