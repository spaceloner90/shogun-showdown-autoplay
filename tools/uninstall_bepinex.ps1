# Removes BepInEx and the mod from the game folder, returning it to its original file set.
# Close the game first. These are the only paths the install added.
param(
    [string]$GameDir = "C:\Program Files\Epic Games\ShogunShowdown611f6"
)

foreach ($name in @("winhttp.dll", "doorstop_config.ini", ".doorstop_version", "changelog.txt", "BepInEx")) {
    $path = Join-Path $GameDir $name
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        "Removed $path"
    }
}
