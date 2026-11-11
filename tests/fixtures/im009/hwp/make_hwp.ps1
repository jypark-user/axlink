# IM-009 시험자료 HWP 세 건(TD-DOC-12·13·15)을 한컴오피스 한글 자동화로 만든다. 가상 시험자료다.
#
#   powershell -ExecutionPolicy Bypass -File tests\fixtures\im009\hwp\make_hwp.ps1 [-Out <폴더>]
#
# 한글(HWPFrame.HwpObject)이 깔린 Windows 에서만 돈다. 만든 파일은 이 폴더에 커밋해 두고 시험은
# 그 파일을 쓴다(files.py). 다시 만들 때만 돌린다. 제작 조건·확인 방법은 README.md.
param([string]$Out = $PSScriptRoot)
$ErrorActionPreference = 'Stop'

# 시험자료 암호. 비밀이 아니다(「암호가 걸린 문서」라는 조건만 필요하다)
$Password = 'axlink-test-1234'

$Paragraphs = @(
    '회의 일시는 2026년 8월 25일 14시이고 장소는 가람시 정보화원 회의실이다.',
    '검토 대상은 SW설계서 v0.9 이며 외부 연계 규격을 중심으로 검토했다.',
    '결론: 지적 사항 2건을 반영해 SW설계서 v1.0 으로 다시 제출한다.'
)
$Table = @(
    @('항목', '검토자', '결과', '비고'),
    @('외부 연계 규격', '김주무관', '보완', '응답 코드 표 추가'),
    @('화면 설계', '박피엠', '적합', '없음')
)

function New-Hwp {
    $h = New-Object -ComObject HWPFrame.HwpObject
    [void]$h.RegisterModule('FilePathCheckDLL', 'FilePathCheckerModule')
    $h
}

function Run([object]$h, [string]$name) { [void]$h.Run($name) }

function Write-Text([object]$h, [string]$text) {
    $a = $h.CreateAction('InsertText'); $s = $a.CreateSet(); [void]$a.GetDefault($s)
    $s.SetItem('Text', $text); [void]$a.Execute($s)
}

function Write-Doc([object]$h, [string]$tid) {
    Write-Text $h "가상 시험자료 · 실제 계약 문서가 아님 · AX Link 검증용(IM-009 $tid)"
    Run $h 'BreakPara'
    Write-Text $h '설계검토회의록'
    Run $h 'BreakPara'
    Write-Text $h $Paragraphs[0]
    Run $h 'BreakPara'
    Write-Text $h $Paragraphs[1]
    Run $h 'BreakPara'
    # 표 1개: 3행 × 4열(머리글 1행 + 자료 2행)
    $a = $h.CreateAction('TableCreate'); $s = $a.CreateSet(); [void]$a.GetDefault($s)
    $s.SetItem('Rows', $Table.Count); $s.SetItem('Cols', 4); $s.SetItem('WidthType', 2); $s.SetItem('HeightType', 0)
    [void]$a.Execute($s)
    for ($r = 0; $r -lt $Table.Count; $r++) {
        for ($c = 0; $c -lt 4; $c++) {
            Write-Text $h $Table[$r][$c]
            if (-not ($r -eq $Table.Count - 1 -and $c -eq 3)) { Run $h 'TableRightCell' }
        }
    }
    Run $h 'Cancel'
    Run $h 'MoveDocEnd'
    Run $h 'BreakPara'
    # 2쪽
    Run $h 'BreakPage'
    Write-Text $h $Paragraphs[2]
}

function Save([object]$h, [string]$path, [string]$format) {
    if (Test-Path $path) { Remove-Item $path }
    if (-not $h.SaveAs($path, $format, '')) { throw "저장 실패: $path" }
}

$h = New-Hwp
try {
    Write-Doc $h 'TD-DOC-12'
    Save $h (Join-Path $Out '설계검토회의록.hwp') 'HWP'
    Save $h (Join-Path $Out '설계검토회의록.hwpx') 'HWPX'
    # TD-DOC-15: 같은 내용에 문서 암호를 건 HWP 5.0
    $a = $h.CreateAction('FilePasswordChange'); $s = $a.CreateSet(); [void]$a.GetDefault($s)
    $s.SetItem('String', $Password); $s.SetItem('Ask', 0)
    [void]$a.Execute($s)
    Save $h (Join-Path $Out '암호문서.hwp') 'HWP'
} finally {
    [void]$h.Clear(1)
    $h.Quit()
}
'완료'
