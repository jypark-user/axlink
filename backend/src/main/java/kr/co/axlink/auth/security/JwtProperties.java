package kr.co.axlink.auth.security;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("axlink.security.jwt")
public record JwtProperties(
    @DefaultValue("") String secret,
    @DefaultValue("axlink") String issuer,
    @DefaultValue("PT30M") Duration accessTtl,
    @DefaultValue("P14D") Duration refreshTtl) {
}
