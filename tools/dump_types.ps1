# Dumps type/field/method signatures from the game's Assembly-CSharp.dll to a text file.
# Uses reflection-only loading, so no game code runs and the install is not modified.
param(
    [string]$GameDir = "C:\Program Files\Epic Games\ShogunShowdown611f6",
    [string]$OutFile = (Join-Path $PSScriptRoot "..\research\types.txt")
)

$managed = Join-Path $GameDir "ShogunShowdown_Data\Managed"

[AppDomain]::CurrentDomain.add_ReflectionOnlyAssemblyResolve({
    param($sender, $resolveArgs)
    $name = (New-Object System.Reflection.AssemblyName($resolveArgs.Name)).Name
    $candidate = Join-Path $managed "$name.dll"
    if (Test-Path $candidate) {
        return [System.Reflection.Assembly]::ReflectionOnlyLoadFrom($candidate)
    }
    return [System.Reflection.Assembly]::ReflectionOnlyLoad($resolveArgs.Name)
})

$asm = [System.Reflection.Assembly]::ReflectionOnlyLoadFrom((Join-Path $managed "Assembly-CSharp.dll"))

try {
    $types = $asm.GetTypes()
} catch [System.Reflection.ReflectionTypeLoadException] {
    Write-Warning "Some types failed to load: $($_.Exception.LoaderExceptions.Count)"
    $types = $_.Exception.Types | Where-Object { $_ -ne $null }
}

$flags = [System.Reflection.BindingFlags]"Public,NonPublic,Instance,Static,DeclaredOnly"
$lines = New-Object System.Collections.Generic.List[string]

function Safe-TypeName($getter) {
    try { return (& $getter).Name } catch { return "?" }
}

foreach ($t in ($types | Sort-Object FullName)) {
    if ($t.FullName -match "<|PrivateImplementationDetails") { continue }
    $base = Safe-TypeName { $t.BaseType }
    $lines.Add("")
    $lines.Add("TYPE $($t.FullName) : $base")
    try {
        foreach ($f in $t.GetFields($flags)) {
            if ($f.Name -match "<") { continue }
            $lines.Add("  F $(Safe-TypeName { $f.FieldType }) $($f.Name)")
        }
        foreach ($p in $t.GetProperties($flags)) {
            $lines.Add("  P $(Safe-TypeName { $p.PropertyType }) $($p.Name)")
        }
        foreach ($m in $t.GetMethods($flags)) {
            if ($m.Name -match "<|^get_|^set_") { continue }
            $params = try { ($m.GetParameters() | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ", " } catch { "?" }
            $lines.Add("  M $(Safe-TypeName { $m.ReturnType }) $($m.Name)($params)")
        }
    } catch {
        $lines.Add("  ! failed: $($_.Exception.Message)")
    }
}

New-Item -ItemType Directory -Force (Split-Path $OutFile) | Out-Null
[System.IO.File]::WriteAllLines([System.IO.Path]::GetFullPath($OutFile), $lines)
"Wrote $($lines.Count) lines covering $($types.Count) types to $OutFile"
