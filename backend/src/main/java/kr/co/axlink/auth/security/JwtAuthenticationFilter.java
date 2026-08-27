package kr.co.axlink.auth.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.co.axlink.auth.domain.AuthPrincipal;
import kr.co.axlink.common.error.ApiException;
import kr.co.axlink.common.error.ErrorCode;
import kr.co.axlink.org.domain.OrgType;
import kr.co.axlink.org.domain.Role;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

  private static final String BEARER = "Bearer ";

  private final JwtCodec jwtCodec;
  private final SecurityErrorWriter errorWriter;
  private final SecurityContextRepository securityContextRepository =
      new RequestAttributeSecurityContextRepository();

  public JwtAuthenticationFilter(JwtCodec jwtCodec, SecurityErrorWriter errorWriter) {
    this.jwtCodec = jwtCodec;
    this.errorWriter = errorWriter;
  }

  @Override
  protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
      FilterChain filterChain) throws ServletException, IOException {
    String header = request.getHeader(HttpHeaders.AUTHORIZATION);
    if (header == null || !header.startsWith(BEARER)) {
      filterChain.doFilter(request, response);
      return;
    }
    try {
      Map<String, Object> claims = jwtCodec.verify(header.substring(BEARER.length()).trim());
      AuthPrincipal principal = toPrincipal(claims);
      UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
          principal, null,
          List.of(new SimpleGrantedAuthority("ROLE_" + principal.role().name())));
      authentication.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
      SecurityContext context = SecurityContextHolder.createEmptyContext();
      context.setAuthentication(authentication);
      SecurityContextHolder.setContext(context);
      securityContextRepository.saveContext(context, request, response);
    } catch (ApiException e) {
      SecurityContextHolder.clearContext();
      errorWriter.write(request, response, e.code(), e.getMessage());
      return;
    } catch (RuntimeException e) {
      SecurityContextHolder.clearContext();
      errorWriter.write(request, response, ErrorCode.AUTH_TOKEN_INVALID, null);
      return;
    }
    filterChain.doFilter(request, response);
  }

  private static AuthPrincipal toPrincipal(Map<String, Object> claims) {
    return new AuthPrincipal(
        UUID.fromString(String.valueOf(claims.get("sub"))),
        UUID.fromString(String.valueOf(claims.get("orgId"))),
        OrgType.valueOf(String.valueOf(claims.get("orgType"))),
        Role.valueOf(String.valueOf(claims.get("role"))));
  }
}
