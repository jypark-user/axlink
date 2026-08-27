package kr.co.axlink.support;

import java.util.UUID;
import java.util.function.Supplier;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Role;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@SpringBootTest
@ActiveProfiles("test")
public abstract class AbstractIntegrationTest {

  protected static final UUID SEED_CLIENT_ORG_ID =
      UUID.fromString("a0000000-0000-4000-8000-000000000002");
  protected static final UUID SEED_CONTRACTOR_ORG_ID =
      UUID.fromString("a0000000-0000-4000-8000-000000000003");
  protected static final UUID SEED_ADMIN_USER_ID =
      UUID.fromString("b0000000-0000-4000-8000-000000000001");
  protected static final UUID SEED_CLIENT_USER_ID =
      UUID.fromString("b0000000-0000-4000-8000-000000000002");
  protected static final UUID SEED_CONTRACTOR_USER_ID =
      UUID.fromString("b0000000-0000-4000-8000-000000000003");
  protected static final UUID SEED_PROJECT_ID =
      UUID.fromString("c0000000-0000-4000-8000-000000000001");

  protected static AuthPrincipal adminPrincipal() {
    return new AuthPrincipal(SEED_ADMIN_USER_ID,
        UUID.fromString("a0000000-0000-4000-8000-000000000001"), OrgType.CLIENT, Role.SUPER_ADMIN);
  }

  protected static AuthPrincipal clientPrincipal() {
    return new AuthPrincipal(SEED_CLIENT_USER_ID, SEED_CLIENT_ORG_ID, OrgType.CLIENT, Role.CLIENT);
  }

  protected static AuthPrincipal contractorPrincipal() {
    return new AuthPrincipal(SEED_CONTRACTOR_USER_ID, SEED_CONTRACTOR_ORG_ID, OrgType.CONTRACTOR,
        Role.CONTRACTOR);
  }

  protected static <T> T inRequestScope(Supplier<T> action) {
    RequestContextHolder.setRequestAttributes(
        new ServletRequestAttributes(new MockHttpServletRequest()));
    try {
      return action.get();
    } finally {
      RequestContextHolder.resetRequestAttributes();
    }
  }
}
