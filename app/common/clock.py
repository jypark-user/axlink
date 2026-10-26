"""사업 기준일 (점검 TIME-01).

"오늘" 은 서버 시간대가 아니라 사업 시간대(Asia/Seoul)의 날짜다. 서버가 UTC 로 돌면
date.today() 는 한국 시각 00~09시에 어제를 내서, 화면의 오늘 계획선과 스케줄러가 찍은 일별
스냅샷 날짜가 어긋났다. 오늘이 필요한 곳은 모두 today() 를 쓴다. 사업별 시간대 설정은 없다
(대상 사업이 모두 국내다). 생기면 여기서 사업을 받아 고른다.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

PROJECT_TZ = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    """지금(UTC). 시험은 이것을 바꿔 날짜 경계를 본다."""
    return datetime.now(UTC)


def today(at: datetime | None = None) -> date:
    """사업 시간대의 날짜. at 이 없으면 지금."""
    return (at or now()).astimezone(PROJECT_TZ).date()
