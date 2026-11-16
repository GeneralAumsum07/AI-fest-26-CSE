# Export each slide of the deck to PNG through real PowerPoint (COM), for
# visual QA. Real PowerPoint is used rather than LibreOffice because the deck
# names Bahnschrift / Segoe UI and only Office renders them true to width.
# Usage: powershell -File export.ps1 <deck.pptx> <outDir>
param([string]$Deck, [string]$OutDir)
$Deck = (Resolve-Path $Deck).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$app = New-Object -ComObject PowerPoint.Application
try {
  # Open read-only, untitled, without a window: nothing on screen, no lock file.
  $p = $app.Presentations.Open($Deck, $true, $true, $false)
  foreach ($s in $p.Slides) {
    $s.Export((Join-Path $OutDir ("slide{0}.png" -f $s.SlideIndex)), "PNG", 1600, 900)
  }
  $p.Close()
} finally {
  $app.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
