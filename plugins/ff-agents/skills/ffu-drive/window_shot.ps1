# Capture a running `ffu` window's own pixels on Windows, even while other windows cover it (w3321).
#   powershell -NoProfile -File window_shot.ps1 -Out shot.png [-ProcessName ffu]
# A desktop grab (CopyFromScreen) on BEAST shows whatever sits on top: in w3321 it caught another sandbox's Unity
# editor and none of the client. PrintWindow with PW_CLIENTONLY | PW_RENDERFULLCONTENT (3) asks the window itself to
# draw, which works for the wgpu (DX12/Vulkan) window while it is covered. It never brings the window to the front, so
# no other sandbox loses focus. An all-black or ~100-byte PNG means the window had closed or was minimised.
param([Parameter(Mandatory = $true)][string]$Out, [string]$ProcessName = "ffu")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class FfuShot {
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  public struct RECT { public int L, T, R, B; }
}
"@
$p = Get-Process $ProcessName -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { throw "window_shot: no $ProcessName process with a window" }
$r = New-Object FfuShot+RECT
[FfuShot]::GetClientRect($p.MainWindowHandle, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ([Math]::Max(1, $r.R)), ([Math]::Max(1, $r.B))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc()
[FfuShot]::PrintWindow($p.MainWindowHandle, $dc, 3) | Out-Null
$g.ReleaseHdc($dc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
"window_shot: $Out ($($r.R)x$($r.B), '$($p.MainWindowTitle)', pid $($p.Id))"
