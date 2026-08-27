package kr.co.axlink.auth.domain;

import java.util.UUID;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Role;

public record AuthPrincipal(UUID userId, UUID organizationId, OrgType orgType, Role role) {
}
