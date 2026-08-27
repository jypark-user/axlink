package kr.co.axlink.org.web;

import java.time.Instant;
import java.util.UUID;
import kr.co.axlink.org.domain.OrgType;

public record OrganizationResponse(
    UUID id,
    String name,
    OrgType type,
    String businessNo,
    long userCount,
    long projectCount,
    Instant createdAt) {
}
