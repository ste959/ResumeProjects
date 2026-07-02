package com.bonddesk.oms.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI omsOpenApi() {
        return new OpenAPI().info(new Info()
                .title("BondDesk OMS API")
                .version("1.0.0")
                .description("""
                        REST API for a Fixed Income Order & Execution Management System.
                        Stage bond orders, run pre-trade compliance, route to a venue,
                        capture fills, and track portfolio positions.""")
                .license(new License().name("MIT")));
    }
}
