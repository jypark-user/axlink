package kr.co.axlink.config;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableAsync
@EnableScheduling
public class AsyncConfig {

  @Bean
  TaskExecutor syncExecutor() {
    return pool("axlink-sync-", 2, 32);
  }

  @Bean
  TaskExecutor documentExecutor() {
    return pool("axlink-doc-", 2, 64);
  }

  @Bean
  TaskExecutor ragExecutor() {
    return pool("axlink-rag-", 8, 32);
  }

  @Bean
  ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("axlink-sched-");
    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.initialize();
    return scheduler;
  }

  @Bean(destroyMethod = "shutdown")
  ScheduledExecutorService sseHeartbeatScheduler() {
    return Executors.newScheduledThreadPool(1, runnable -> {
      Thread thread = new Thread(runnable, "axlink-sse-heartbeat");
      thread.setDaemon(true);
      return thread;
    });
  }

  private static ThreadPoolTaskExecutor pool(String prefix, int threads, int queueCapacity) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(threads);
    executor.setMaxPoolSize(threads);
    executor.setQueueCapacity(queueCapacity);
    executor.setThreadNamePrefix(prefix);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.initialize();
    return executor;
  }
}
