import type { ReactNode } from 'react';
import type { WidgetTemplate } from '@/types/api';

/** 위젯 자리의 밑그림 — 무엇이 놓일지 모양으로 먼저 알려 준다. */
const SKETCH: Record<WidgetTemplate, ReactNode> = {
  STAT_CARD: (
    <>
      <rect x="4" y="10" width="26" height="12" rx="2" className="fill-primary/50" />
      <rect x="4" y="26" width="40" height="4" rx="2" className="fill-muted-foreground/30" />
    </>
  ),
  BAR_CHART: (
    <>
      <rect x="5" y="18" width="7" height="14" rx="1" className="fill-primary/50" />
      <rect x="16" y="10" width="7" height="22" rx="1" className="fill-primary/50" />
      <rect x="27" y="22" width="7" height="10" rx="1" className="fill-primary/50" />
      <rect x="38" y="14" width="7" height="18" rx="1" className="fill-primary/50" />
    </>
  ),
  LINE_CHART: (
    <polyline
      points="5,28 16,18 26,23 36,10 45,14"
      fill="none"
      strokeWidth="2.5"
      className="stroke-primary/60"
    />
  ),
  PIE_CHART: (
    <>
      <circle cx="25" cy="20" r="11" fill="none" strokeWidth="6" className="stroke-muted" />
      <circle
        cx="25"
        cy="20"
        r="11"
        fill="none"
        strokeWidth="6"
        strokeDasharray="46 69"
        strokeLinecap="round"
        transform="rotate(-90 25 20)"
        className="stroke-primary/60"
      />
    </>
  ),
  PROGRESS_LIST: (
    <>
      <rect x="4" y="10" width="42" height="4" rx="2" className="fill-muted" />
      <rect x="4" y="10" width="30" height="4" rx="2" className="fill-primary/50" />
      <rect x="4" y="19" width="42" height="4" rx="2" className="fill-muted" />
      <rect x="4" y="19" width="18" height="4" rx="2" className="fill-primary/50" />
      <rect x="4" y="28" width="42" height="4" rx="2" className="fill-muted" />
      <rect x="4" y="28" width="36" height="4" rx="2" className="fill-primary/50" />
    </>
  ),
  DATA_TABLE: (
    <>
      <rect x="4" y="8" width="42" height="5" rx="1" className="fill-muted-foreground/30" />
      <rect x="4" y="17" width="42" height="4" rx="1" className="fill-muted" />
      <rect x="4" y="24" width="42" height="4" rx="1" className="fill-muted" />
      <rect x="4" y="31" width="42" height="4" rx="1" className="fill-muted" />
      <line x1="18" y1="8" x2="18" y2="35" strokeWidth="1" className="stroke-background" />
      <line x1="32" y1="8" x2="32" y2="35" strokeWidth="1" className="stroke-background" />
    </>
  ),
  CHECKLIST: (
    <>
      <rect x="4" y="9" width="6" height="6" rx="1.5" className="fill-primary/50" />
      <rect x="14" y="10" width="32" height="4" rx="2" className="fill-muted" />
      <rect x="4" y="19" width="6" height="6" rx="1.5" className="fill-primary/50" />
      <rect x="14" y="20" width="26" height="4" rx="2" className="fill-muted" />
      <rect x="4" y="29" width="6" height="6" rx="1.5" className="fill-muted" />
      <rect x="14" y="30" width="30" height="4" rx="2" className="fill-muted" />
    </>
  ),
  GANTT_SUMMARY: (
    <>
      <rect x="4" y="10" width="24" height="5" rx="2" className="fill-primary/50" />
      <rect x="14" y="19" width="24" height="5" rx="2" className="fill-primary/40" />
      <rect x="26" y="28" width="20" height="5" rx="2" className="fill-primary/30" />
    </>
  ),
  STATUS_FLOW: (
    <>
      <rect x="4" y="14" width="16" height="8" rx="2" className="fill-primary/60" />
      <rect x="21" y="14" width="11" height="8" className="fill-primary/40" />
      <rect x="33" y="14" width="13" height="8" rx="2" className="fill-primary/20" />
      <rect x="4" y="27" width="30" height="3" rx="1.5" className="fill-muted-foreground/30" />
    </>
  ),
  HEATMAP: (
    <>
      {[0, 1, 2, 3].map((col) =>
        [0, 1, 2].map((row) => (
          <rect
            key={`${col}-${row}`}
            x={6 + col * 10}
            y={10 + row * 8}
            width="8"
            height="6"
            rx="1"
            className={
              (col + row) % 3 === 0
                ? 'fill-primary/60'
                : (col + row) % 3 === 1
                  ? 'fill-primary/30'
                  : 'fill-muted-foreground/20'
            }
          />
        )),
      )}
    </>
  ),
  AREA_CHART: (
    <>
      <path d="M5 30 L16 18 L26 23 L36 11 L45 15 L45 32 L5 32 Z" className="fill-primary/30" />
      <polyline
        points="5,30 16,18 26,23 36,11 45,15"
        fill="none"
        strokeWidth="2.5"
        className="stroke-primary/60"
      />
    </>
  ),
  STACKED_BAR_CHART: (
    <>
      {[5, 16, 27, 38].map((x, i) => (
        <g key={x}>
          <rect
            x={x}
            y={22 - i * 2}
            width="7"
            height={10 + i * 2}
            rx="1"
            className="fill-primary/30"
          />
          <rect x={x} y={14 - i * 2} width="7" height="8" rx="1" className="fill-primary/60" />
        </g>
      ))}
    </>
  ),
  HORIZONTAL_BAR_CHART: (
    <>
      <rect x="5" y="9" width="34" height="6" rx="1" className="fill-primary/60" />
      <rect x="5" y="18" width="22" height="6" rx="1" className="fill-primary/45" />
      <rect x="5" y="27" width="29" height="6" rx="1" className="fill-primary/30" />
    </>
  ),
  DONUT_CHART: (
    <>
      <circle cx="25" cy="20" r="11" fill="none" strokeWidth="6" className="stroke-muted" />
      <circle
        cx="25"
        cy="20"
        r="11"
        fill="none"
        strokeWidth="6"
        strokeDasharray="30 39"
        strokeLinecap="round"
        transform="rotate(-90 25 20)"
        className="stroke-primary/60"
      />
      <circle cx="25" cy="20" r="5" className="fill-background" />
    </>
  ),
  RADAR_CHART: (
    <>
      <polygon
        points="25,7 40,18 34,33 16,33 10,18"
        fill="none"
        strokeWidth="1"
        className="stroke-muted-foreground/30"
      />
      <polygon points="25,12 35,19 31,29 19,28 15,19" className="fill-primary/40" />
    </>
  ),
  CUMULATIVE_FLOW: (
    <>
      <path d="M5,32 L15,26 L25,20 L35,13 L45,8 L45,32 Z" className="fill-primary/45" />
      <path d="M5,32 L15,30 L25,27 L35,24 L45,22 L45,32 Z" className="fill-primary/70" />
    </>
  ),
  PARETO: (
    <>
      <rect x="5" y="12" width="7" height="20" rx="1" className="fill-primary/50" />
      <rect x="15" y="18" width="7" height="14" rx="1" className="fill-primary/50" />
      <rect x="25" y="24" width="7" height="8" rx="1" className="fill-primary/50" />
      <rect x="35" y="28" width="7" height="4" rx="1" className="fill-primary/50" />
      <polyline
        points="8,22 18,15 28,11 38,9"
        fill="none"
        strokeWidth="2"
        className="stroke-muted-foreground/60"
      />
    </>
  ),
  TREEMAP: (
    <>
      <rect x="5" y="8" width="22" height="15" rx="1" className="fill-primary/60" />
      <rect x="29" y="8" width="16" height="15" rx="1" className="fill-primary/40" />
      <rect x="5" y="25" width="13" height="8" rx="1" className="fill-primary/30" />
      <rect x="20" y="25" width="12" height="8" rx="1" className="fill-primary/25" />
      <rect x="34" y="25" width="11" height="8" rx="1" className="fill-primary/20" />
    </>
  ),
  SLOPE_CHART: (
    <>
      <line x1="12" y1="10" x2="38" y2="26" strokeWidth="2" className="stroke-primary/60" />
      <line x1="12" y1="20" x2="38" y2="12" strokeWidth="2" className="stroke-primary/35" />
      <circle cx="12" cy="10" r="2.5" className="fill-primary/70" />
      <circle cx="38" cy="26" r="2.5" className="fill-primary/70" />
      <circle cx="12" cy="20" r="2.5" className="fill-primary/40" />
      <circle cx="38" cy="12" r="2.5" className="fill-primary/40" />
    </>
  ),
  BUMP_CHART: (
    <>
      <polyline
        points="6,10 18,10 30,20 42,26"
        fill="none"
        strokeWidth="2"
        className="stroke-primary/60"
      />
      <polyline
        points="6,20 18,26 30,10 42,10"
        fill="none"
        strokeWidth="2"
        className="stroke-primary/30"
      />
    </>
  ),
  SPARKLINE: (
    <>
      <polyline
        points="5,14 13,10 21,15 29,8 37,12"
        fill="none"
        strokeWidth="2"
        className="stroke-primary/60"
      />
      <rect x="40" y="9" width="6" height="4" rx="1" className="fill-muted-foreground/30" />
      <polyline
        points="5,28 13,25 21,29 29,22 37,26"
        fill="none"
        strokeWidth="2"
        className="stroke-primary/35"
      />
      <rect x="40" y="23" width="6" height="4" rx="1" className="fill-muted-foreground/30" />
    </>
  ),
  BULLET_CHART: (
    <>
      <rect x="5" y="11" width="40" height="6" rx="2" className="fill-muted" />
      <rect x="5" y="11" width="26" height="6" rx="2" className="fill-primary/60" />
      <rect x="35" y="9" width="2" height="10" className="fill-foreground/70" />
      <rect x="5" y="24" width="40" height="6" rx="2" className="fill-muted" />
      <rect x="5" y="24" width="34" height="6" rx="2" className="fill-primary/40" />
      <rect x="30" y="22" width="2" height="10" className="fill-foreground/70" />
    </>
  ),
  CALENDAR_HEATMAP: (
    <>
      {[0, 1, 2, 3, 4, 5, 6, 7].map((col) =>
        [0, 1, 2, 3].map((row) => (
          <rect
            key={`${col}-${row}`}
            x={5 + col * 5.2}
            y={10 + row * 5.2}
            width="4"
            height="4"
            rx="1"
            className={(col + row) % 3 === 0 ? 'fill-primary/60' : 'fill-muted'}
          />
        )),
      )}
    </>
  ),
};

export function WidgetSketch({ template }: { template: WidgetTemplate }): ReactNode {
  return (
    <svg viewBox="0 0 50 40" aria-hidden className="h-10 w-full">
      {SKETCH[template]}
    </svg>
  );
}
