/**
 * num_predict 권장값 계산 (ARC-011). 순수 함수다. 화면은 이 문장을 그대로 보여 준다.
 *
 * 한 턴의 최장 소요 시간은 num_predict ÷ 생성 속도다. 그것이 요청 시간 제한을 넘으면
 * 프록시가 504 로 끊는다. 속도를 모를 때는 숫자를 지어내지 않는다.
 */

export interface AdviceInput {
  /** 실측 생성 속도(tok/s). 0 이면 미측정 */
  rate: number;
  /** 현재 num_predict */
  predict: number;
  /** 한 요청이 쓸 수 있는 초. 0 이면 미설정 */
  limit: number;
  /** 접두 캐시가 깨졌을 때의 프리필과 도구 왕복 몫(초). 기본 150 */
  reserve?: number;
}

export type AdviceLevel = 'unmeasured' | 'unbounded' | 'warn' | 'ok';

export interface Advice {
  level: AdviceLevel;
  text: string;
  /** 권장 상한. 계산할 수 없으면 null */
  advised: number | null;
  /** 최악 소요 초. 속도를 모르면 null */
  worstSeconds: number | null;
}

export const DEFAULT_RESERVE_SECONDS = 150;

const fmtRate = (rate: number): string => rate.toFixed(1);
const fmtSec = (sec: number): string => String(Math.ceil(sec));
const fmtInt = (n: number): string => n.toLocaleString('ko-KR');

export function adviseNumPredict({
  rate,
  predict,
  limit,
  reserve = DEFAULT_RESERVE_SECONDS,
}: AdviceInput): Advice {
  if (!(rate > 0)) {
    return {
      level: 'unmeasured',
      advised: null,
      worstSeconds: null,
      text: "생성 속도를 아직 재지 않았습니다. '이 서버에서 재보기'를 누르세요.",
    };
  }
  const worst = predict / rate;
  if (!(limit > 0)) {
    return {
      level: 'unbounded',
      advised: null,
      worstSeconds: worst,
      text:
        `실측 ${fmtRate(rate)} tok/s. 현재 값 ${fmtInt(predict)}은 최악 ${fmtSec(worst)}초가 걸립니다. ` +
        '요청 시간 제한이 설정돼 있지 않으니 프록시 read timeout이 이보다 큰지 확인하세요.',
    };
  }
  const budget = Math.max(limit - reserve, 0);
  const advised = Math.floor((budget * rate) / 1000) * 1000;
  const head = `실측 ${fmtRate(rate)} tok/s · 시간 제한 ${fmtSec(limit)}초 → 권장 ${fmtInt(advised)} 이하.`;
  if (worst > budget) {
    return {
      level: 'warn',
      advised,
      worstSeconds: worst,
      text:
        `⚠ ${head} 현재 값 ${fmtInt(predict)}은 최악 ${fmtSec(worst)}초라 ${fmtSec(limit)}초 상한을 넘겨 ` +
        `504로 끊깁니다. 값을 낮추거나 시간 제한과 프록시 read timeout을 ${fmtSec(worst + reserve)}초로 올리세요.`,
    };
  }
  const percent = Math.round((worst * 100) / limit);
  return {
    level: 'ok',
    advised,
    worstSeconds: worst,
    text: `${head} 현재 값 ${fmtInt(predict)}은 최악 ${fmtSec(worst)}초. 상한의 ${percent}%로 여유가 있습니다.`,
  };
}
