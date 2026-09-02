-- 그래프 템플릿 확장. 기존 제약이 8종에서 멈춰 있어 STATUS_FLOW·HEATMAP 위젯을 저장할 수 없었다.
alter table widget drop constraint ck_widget__template;
alter table widget add constraint ck_widget__template check (template in (
  'STAT_CARD','BAR_CHART','LINE_CHART','PIE_CHART','PROGRESS_LIST','DATA_TABLE',
  'CHECKLIST','GANTT_SUMMARY','STATUS_FLOW','HEATMAP',
  'AREA_CHART','STACKED_BAR_CHART','HORIZONTAL_BAR_CHART','DONUT_CHART','RADAR_CHART'));
