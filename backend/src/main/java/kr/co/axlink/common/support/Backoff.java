package kr.co.axlink.common.support;

import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Predicate;

public final class Backoff {

  private Backoff() {
  }

  public record BackoffPolicy(int maxAttempts, Duration initial, Duration max) {
  }

  public static <T> T retry(BackoffPolicy p, Callable<T> op, Predicate<Exception> retryable) {
    long delayMillis = p.initial().toMillis();
    Exception last = null;
    for (int attempt = 1; attempt <= p.maxAttempts(); attempt++) {
      try {
        return op.call();
      } catch (Exception e) {
        last = e;
        if (attempt == p.maxAttempts() || !retryable.test(e)) {
          break;
        }
        sleep(jitter(Math.min(delayMillis, p.max().toMillis())));
        delayMillis = Math.min(delayMillis * 2, p.max().toMillis());
      }
    }
    if (last instanceof RuntimeException runtime) {
      throw runtime;
    }
    throw new IllegalStateException(last);
  }

  private static long jitter(long millis) {
    long span = Math.max(1, millis / 5);
    return millis + ThreadLocalRandom.current().nextLong(-span, span + 1);
  }

  private static void sleep(long millis) {
    try {
      Thread.sleep(Math.max(0, millis));
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(e);
    }
  }
}
