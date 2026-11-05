# Dumps all types, enum values, fields, properties and method IL from Assembly-CSharp.dll using Mono.Cecil.
# Static read only: no game code runs. Replaces the reflection dump, which skips types using
# default interface methods because .NET Framework reflection cannot load them.
param(
    [Parameter(Mandatory=$true)][string]$CecilPath,
    [string]$GameDir = "C:\Program Files\Epic Games\ShogunShowdown611f6",
    [string]$OutDir
)

if (-not $OutDir) { $OutDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\research" }

Add-Type -Path $CecilPath
$dll = Join-Path $GameDir "ShogunShowdown_Data\Managed\Assembly-CSharp.dll"
$module = [Mono.Cecil.ModuleDefinition]::ReadModule($dll)

New-Item -ItemType Directory -Force $OutDir | Out-Null
$outPath = Join-Path ([System.IO.Path]::GetFullPath($OutDir)) "il.txt"
$w = New-Object System.IO.StreamWriter($outPath, $false)

function Write-Type($t) {
    $base = if ($t.BaseType) { $t.BaseType.Name } else { "" }
    $w.WriteLine("")
    $w.WriteLine("TYPE $($t.FullName) : $base")
    foreach ($f in $t.Fields) {
        $static = if ($f.IsStatic) { "static " } else { "" }
        $const = if ($f.HasConstant) { " = $($f.Constant)" } else { "" }
        $w.WriteLine("  F $static$($f.FieldType.Name) $($f.Name)$const")
    }
    foreach ($p in $t.Properties) {
        $w.WriteLine("  P $($p.PropertyType.Name) $($p.Name)")
    }
    foreach ($m in $t.Methods) {
        $params = ($m.Parameters | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ", "
        $w.WriteLine("  M $($m.ReturnType.Name) $($m.Name)($params)")
        if ($m.HasBody) {
            foreach ($i in $m.Body.Instructions) {
                $operand = ""
                if ($null -ne $i.Operand) {
                    if ($i.Operand -is [Mono.Cecil.Cil.Instruction]) {
                        $operand = "IL_{0:x4}" -f $i.Operand.Offset
                    } else {
                        $operand = $i.Operand.ToString()
                    }
                }
                $w.WriteLine(("      IL_{0:x4} {1} {2}" -f $i.Offset, $i.OpCode.Name, $operand))
            }
        }
    }
    foreach ($n in $t.NestedTypes) { Write-Type $n }
}

$count = 0
foreach ($t in $module.Types) {
    Write-Type $t
    $count++
}
$w.Close()
"Wrote $outPath for $count top-level types, $([math]::Round((Get-Item $outPath).Length/1MB,1)) MB"
