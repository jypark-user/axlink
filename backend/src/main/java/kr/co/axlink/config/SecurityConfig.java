package kr.co.axlink.config;

import jakarta.servlet.DispatcherType;
import kr.co.axlink.auth.security.JwtAuthenticationFilter;
import kr.co.axlink.auth.security.SecurityErrorWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

  /** 용역사에게 닫는 경로. 화면 메뉴(app-sidebar.tsx / routes.tsx)의 EXCEPT_CONTRACTOR 와 짝이다. */
  private static final String[] EXCEPT_CONTRACTOR = {
      // AI Q&A · LLM
      "/api/conversations/**", "/api/messages/**", "/api/semantic/**",
      // 대시보드 · 위젯
      "/api/dashboards/**", "/api/widgets/**",
      // 발주사 PM 화면
      "/api/projects/*/assignments/**",
      "/api/projects/*/change-requests", "/api/change-requests/**",
      "/api/projects/*/correction-actions", "/api/correction-actions/**",
      "/api/projects/*/progress-records", "/api/projects/*/acceptance-record",
      // 요구사항 추적 · 산출물 점검표
      "/api/projects/*/requirements", "/api/requirements/**",
      "/api/projects/*/work-products", "/api/work-products/**",
      "/api/projects/*/traceability", "/api/projects/*/trace-links", "/api/trace-links/**",
      "/api/projects/*/issues", "/api/projects/*/risks", "/api/entity-history",
      // 자료 관리(업로드 · 구조화)
      "/api/projects/*/documents", "/api/documents/**",
  };

  @Bean
  SecurityFilterChain filterChain(HttpSecurity http, JwtAuthenticationFilter jwtFilter,
      SecurityErrorWriter errorWriter) throws Exception {
    return http
        .csrf(AbstractHttpConfigurer::disable)
        .cors(Customizer.withDefaults())
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable)
        .logout(AbstractHttpConfigurer::disable)
        .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .exceptionHandling(e -> e
            .authenticationEntryPoint(errorWriter)
            .accessDeniedHandler(errorWriter))
        .authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers(HttpMethod.POST, "/api/auth/login", "/api/auth/refresh",
                "/api/auth/invitations/accept").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/auth/invitations/*", "/actuator/health")
            .permitAll()
            // 용역사(CONTRACTOR)는 AI Q&A·LLM 기능과 발주사 화면을 쓰지 않는다.
            // 열려 있는 것은 사업 정보 조회, 도구 연동 등록·연결 상태, 동기화 이력뿐이다.
            .requestMatchers(EXCEPT_CONTRACTOR).hasAnyRole("SUPER_ADMIN", "CLIENT")
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class)
        .build();
  }

  @Bean
  PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(10);
  }
}
