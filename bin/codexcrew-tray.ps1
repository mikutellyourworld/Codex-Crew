# Codex Crew tray launcher.
# Starts the gateway hidden, waits until the dashboard responds, opens it in
# Firefox, and shows a system-tray icon with Open / Restart / Quit. No console
# window: this is launched via wscript -> the .vbs wrapper, and the gateway
# child is started hidden.
param()

$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Repo root = parent of this script's folder (...\Codex Crew\bin -> ...\Codex Crew).
$repo    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe     = Join-Path $repo '.venv\Scripts\codexcrew.exe'
$icoPath = Join-Path $repo 'website\electron\icon.ico'
$firefox = 'C:\Program Files\Mozilla Firefox\firefox.exe'
$url     = 'http://localhost:5486'
$readyUrl = 'http://127.0.0.1:5486/api/ready'

$script:gateway = $null

function Start-Gateway {
    # Start the gateway with no visible window.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = $exe
    $psi.Arguments       = 'gateway'
    $psi.WorkingDirectory = $repo
    $psi.WindowStyle     = 'Hidden'
    $psi.CreateNoWindow  = $true
    $psi.UseShellExecute = $false
    $script:gateway = [System.Diagnostics.Process]::Start($psi)
}

function Test-Ready {
    try {
        return (Invoke-WebRequest -Uri $readyUrl -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200
    } catch { return $false }
}

function Open-Dashboard {
    if (Test-Path $firefox) {
        Start-Process $firefox -ArgumentList $url
    } else {
        Start-Process $url   # fall back to the OS default browser
    }
}

function Stop-Gateway {
    # Kill whatever is listening on 5486 plus our tracked child.
    try {
        $c = Get-NetTCPConnection -LocalPort 5486 -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $c) { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }
    } catch {}
    if ($script:gateway -and -not $script:gateway.HasExited) {
        try { $script:gateway.Kill() } catch {}
    }
}

# --- tray icon + menu --------------------------------------------------------
$icon = if (Test-Path $icoPath) { New-Object System.Drawing.Icon $icoPath } else { [System.Drawing.SystemIcons]::Application }

$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Icon = $icon
$tray.Text = 'Codex Crew'
$tray.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$miOpen = $menu.Items.Add('Open dashboard')
$miOpen.add_Click({ Open-Dashboard })

$miRestart = $menu.Items.Add('Restart gateway')
$miRestart.add_Click({
    Stop-Gateway
    Start-Sleep -Seconds 2
    Start-Gateway
    $tray.ShowBalloonTip(3000, 'Codex Crew', 'Gateway restarting...', 'Info')
})

$menu.Items.Add('-') | Out-Null

$miQuit = $menu.Items.Add('Quit Codex Crew')
$miQuit.add_Click({
    Stop-Gateway
    $tray.Visible = $false
    $tray.Dispose()
    [System.Windows.Forms.Application]::Exit()
})

$tray.ContextMenuStrip = $menu
# Double-clicking the tray icon opens the dashboard.
$tray.add_MouseDoubleClick({ Open-Dashboard })

# --- startup -----------------------------------------------------------------
Start-Gateway
$tray.ShowBalloonTip(3000, 'Codex Crew', 'Starting gateway...', 'Info')

# Poll for readiness on a timer, then open the browser once, then keep the
# tray alive. A WinForms Timer fires on the message loop, so the UI/menu stay
# responsive.
$script:opened = $false
$script:elapsed = 0
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.add_Tick({
    $script:elapsed += 2
    if (-not $script:opened) {
        if (Test-Ready) {
            Open-Dashboard
            $tray.ShowBalloonTip(3000, 'Codex Crew', 'Dashboard ready.', 'Info')
            $script:opened = $true
        } elseif ($script:elapsed -ge 240) {
            # Gave up waiting; stop polling but leave the tray so the user can retry.
            $timer.Stop()
        }
    }
})
$timer.Start()

# Run the message loop (keeps the tray icon and menu alive).
[System.Windows.Forms.Application]::Run()
