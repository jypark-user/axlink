# make_hwp.ps1 로 만든 HWP·HWPX 를 한글로 다시 열어 쪽 수와 형식을 확인한다(암호 문서는 열지 않는다).
#   powershell -ExecutionPolicy Bypass -File tests\fixtures\im009\hwp\check_hwp.ps1 [-Dir <폴더>]
param([string]$Dir = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$h = New-Object -ComObject HWPFrame.HwpObject
[void]$h.RegisterModule('FilePathCheckDLL', 'FilePathCheckerModule')
try {
    foreach ($f in @(@('설계검토회의록.hwp', 'HWP'), @('설계검토회의록.hwpx', 'HWPX'))) {
        $p = Join-Path $Dir $f[0]
        if (-not $h.Open($p, $f[1], 'forceopen:true')) { throw "열기 실패: $p" }
        "{0}: 쪽 {1}" -f $f[0], $h.PageCount
        [void]$h.Clear(1)
    }
} finally {
    $h.Quit()
}
