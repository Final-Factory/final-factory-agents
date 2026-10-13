param(
  [Parameter(Mandatory = $true)][int]$PlayerPid,
  [Parameter(Mandatory = $true)][string]$OutPng,
  [double]$FracX = 0.70,
  [double]$FracY = 0.60,
  [int]$MinIdleSeconds = 60
)
# w980: reads the REAL OS cursor over a built player's window and captures the window with that cursor drawn in.
# Moves the real mouse only when the desktop has been idle for MinIdleSeconds (no person using it), and puts it back.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize, flags; public IntPtr hCursor; public POINT pt; }
  [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize, dwTime; }
  [DllImport("user32.dll")] public static extern bool GetCursorInfo(ref CURSORINFO ci);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr LoadCursor(IntPtr inst, int id);
  [DllImport("user32.dll")] public static extern bool DrawIconEx(IntPtr hdc, int x, int y, IntPtr icon, int w, int h, int step, IntPtr brush, int flags);
  [DllImport("user32.dll")] public static extern bool GetIconInfo(IntPtr icon, out ICONINFO info);
  [StructLayout(LayoutKind.Sequential)] public struct ICONINFO { public bool fIcon; public int xHotspot, yHotspot; public IntPtr hbmMask, hbmColor; }
  [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO li);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
}
"@

[void][W]::SetProcessDPIAware()
$li = New-Object W+LASTINPUTINFO; $li.cbSize = 8
[void][W]::GetLastInputInfo([ref]$li)
$idle = ([Environment]::TickCount - [int]$li.dwTime) / 1000.0
if ($idle -lt $MinIdleSeconds) { Write-Output ("refused: desktop idle only {0:N0} s" -f $idle); exit 2 }

$proc = Get-Process -Id $PlayerPid
$h = $proc.MainWindowHandle
if ($h -eq [IntPtr]::Zero) { Write-Output "refused: player has no main window"; exit 3 }
$cr = New-Object W+RECT; [void][W]::GetClientRect($h, [ref]$cr)
$origin = New-Object W+POINT; [void][W]::ClientToScreen($h, [ref]$origin)
$w = $cr.R - $cr.L; $hgt = $cr.B - $cr.T

$saved = New-Object W+POINT; [void][W]::GetCursorPos([ref]$saved)
[void][W]::ShowWindow($h, 9)
[W]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [W]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
[void][W]::SetForegroundWindow($h)
Start-Sleep -Milliseconds 300
$fg = ([W]::GetForegroundWindow() -eq $h)
$tx = $origin.X + [int]($w * $FracX); $ty = $origin.Y + [int]($hgt * $FracY)
[void][W]::SetCursorPos($tx, $ty)
Start-Sleep -Milliseconds 700
[void][W]::SetCursorPos($tx + 1, $ty)
Start-Sleep -Milliseconds 500

$ci = New-Object W+CURSORINFO; $ci.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($ci)
[void][W]::GetCursorInfo([ref]$ci)
$under = [W]::GetAncestor([W]::WindowFromPoint($ci.pt), 2)
$arrow = [W]::LoadCursor([IntPtr]::Zero, 32512)

# The OS cursor icon alone (a GDI capture of the game window comes back black): 96x96, mid-grey ground.
$bmp = New-Object System.Drawing.Bitmap 96, 96
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(255, 70, 70, 70))
$ii = New-Object W+ICONINFO; [void][W]::GetIconInfo($ci.hCursor, [ref]$ii)
$hdc = $g.GetHdc()
[void][W]::DrawIconEx($hdc, 16, 16, $ci.hCursor, 0, 0, 0, [IntPtr]::Zero, 3)
$g.ReleaseHdc($hdc)
$bmp.Save($OutPng, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()

[void][W]::SetCursorPos($saved.X, $saved.Y)
Write-Output ("foreground=$fg idle={0:N0}s window={1}x{2} cursorAt={3},{4} underPlayer={5} hCursor=0x{6:X} systemArrow=0x{7:X} isSystemArrow={8} hotspot={9},{10} shot={11}" -f `
  $idle, $w, $hgt, $ci.pt.X, $ci.pt.Y, ($under -eq $h), $ci.hCursor.ToInt64(), $arrow.ToInt64(), ($ci.hCursor -eq $arrow), $ii.xHotspot, $ii.yHotspot, $OutPng)
