package com.bonddesk.oms.dto;

import java.util.List;

public record UserInfo(String username, List<String> roles) {}
