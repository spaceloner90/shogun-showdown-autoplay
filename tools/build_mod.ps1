# Compiles mod\*.cs with the C# compiler built into Windows and installs the DLL in BepInEx\plugins.
# The running game locks the installed DLL, so it can't be replaced until the game closes.
# With -WaitForGame this script waits for that (up to 2 hours). Without it, it builds and stops.
param(
    [string]$GameDir = "C:\Program Files\Epic Games\ShogunShowdown611f6",
    [switch]$WaitForGame
)

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$managed = Join-Path $GameDir "ShogunShowdown_Data\Managed"
$core = Join-Path $GameDir "BepInEx\core"
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$outDir = Join-Path $proj "mod\bin"
$out = Join-Path $outDir "ShogunStateLogger.dll"

New-Item -ItemType Directory -Force $outDir | Out-Null

$refs = @(
    "$managed\mscorlib.dll",
    "$managed\netstandard.dll",
    "$managed\System.dll",
    "$managed\System.Core.dll",
    "$managed\UnityEngine.dll",
    "$managed\UnityEngine.CoreModule.dll",
    "$managed\Unity.InputSystem.dll",
    "$managed\Assembly-CSharp.dll",
    "$core\BepInEx.dll",
    "$core\0Harmony.dll"
) | ForEach-Object { "/reference:$_" }

& $csc /nologo /noconfig /nostdlib+ /target:library /optimize+ /warn:1 "/out:$out" @refs (Join-Path $proj "mod\*.cs")
if ($LASTEXITCODE -ne 0) { throw "Compile failed with exit code $LASTEXITCODE" }
"Built $out"

function Test-GameRunning { [bool](Get-Process -Name ShogunShowdown -ErrorAction SilentlyContinue) }

if (Test-GameRunning) {
    if (-not $WaitForGame) {
        "Not installed: the game is running. Close it and run this again, or use -WaitForGame."
        exit 0
    }
    "Waiting for the game to close..."
    $deadline = (Get-Date).AddHours(2)
    while (Test-GameRunning) {
        if ((Get-Date) -gt $deadline) { throw "Timed out waiting for the game to close; nothing installed." }
        Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 1
}

$plugins = Join-Path $GameDir "BepInEx\plugins"
New-Item -ItemType Directory -Force $plugins | Out-Null
Copy-Item $out $plugins -Force
$installed = Get-Item (Join-Path $plugins "ShogunStateLogger.dll")
"Installed $($installed.FullName): $($installed.Length) bytes"
