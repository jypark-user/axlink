package kr.co.axlink.common.crypto;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("axlink.crypto")
public record CryptoProperties(@DefaultValue("") String masterKey) {
}
