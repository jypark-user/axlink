package kr.co.axlink.integration.adapter;

import kr.co.axlink.integration.port.SyncPromoter;
import kr.co.axlink.integration.service.NoOpSyncPromoter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IntegrationAdapterConfiguration {

  @Bean
  @ConditionalOnMissingBean(SyncPromoter.class)
  public SyncPromoter noOpSyncPromoter() {
    return new NoOpSyncPromoter();
  }
}
