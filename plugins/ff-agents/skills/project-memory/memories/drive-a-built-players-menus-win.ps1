param([int]$procId, [string]$action, [double]$x = 0, [double]$y = 0, [string]$text = "")
# Drive a game window with real input. x,y are in client pixels of a 1600x900 reference; scaled to the client size.
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(int f, int dx, int dy, int d, IntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, int flags, IntPtr e);
}
"@
Add-Type -AssemblyName System.Windows.Forms
$h = (Get-Process -Id $procId).MainWindowHandle
[W]::ShowWindow($h, 9) | Out-Null
# Alt tap lets SetForegroundWindow succeed from a background process.
[W]::keybd_event(0x12, 0, 0, [IntPtr]::Zero); [W]::keybd_event(0x12, 0, 2, [IntPtr]::Zero)
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 300
$r = New-Object W+RECT; [W]::GetClientRect($h, [ref]$r) | Out-Null
$p = New-Object W+POINT
$p.X = [int]($x * ($r.R - $r.L) / 1600); $p.Y = [int]($y * ($r.B - $r.T) / 900)
[W]::ClientToScreen($h, [ref]$p) | Out-Null
switch ($action) {
  "click" {
    [W]::SetCursorPos($p.X, $p.Y); Start-Sleep -Milliseconds 150
    [W]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero); Start-Sleep -Milliseconds 80
    [W]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
    "clicked $x,$y -> screen $($p.X),$($p.Y) client $($r.R)x$($r.B)"
  }
  "type" { [System.Windows.Forms.SendKeys]::SendWait($text); "typed" }
  "key" { [System.Windows.Forms.SendKeys]::SendWait($text); "key $text" }
}
