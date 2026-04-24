[CmdletBinding()]
param(
    [string]$TemplatePath = 'C:\Daten\Python\vobes_agent_vscode\.agents\skills\skill-powerpoint-ppt-cli\Vorlagen\Volkswagen Brand.potx',
    [string]$OutputPath   = 'C:\Daten\Python\vobes_agent_vscode\userdata\powerpoint\drafts\test_email_prompt_next_sentence.pptx',
    [string]$MappingPath  = 'C:\Daten\Python\vobes_agent_vscode\.agents\skills\skill-powerpoint-ppt-cli\mappings\volkswagen_brand.layout_mapping.json',
    [string]$ContentPath  = 'C:\Daten\Python\vobes_agent_vscode\.agents\skills\skill-powerpoint-ppt-cli\scripts\data\test_email_prompt_content.json'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Info([string]$m) { [Console]::Error.WriteLine("[build] $m") }
function Fail([string]$m) { [Console]::Error.WriteLine("[build][ERROR] $m"); exit 1 }

function Resolve-ContentRelativePath {
    param(
        [string]$Path,
        [string]$BaseDir
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return (Join-Path $BaseDir $Path)
}

function Get-PropValue {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $null
}

function Get-CustomLayout {
    param(
        $Presentation,
        [string[]]$PreferredNames,
        [string[]]$ContainsHints
    )

    $layouts = $Presentation.SlideMaster.CustomLayouts

    foreach ($name in $PreferredNames) {
        for ($i = 1; $i -le $layouts.Count; $i++) {
            $layout = $layouts.Item($i)
            if ($layout.Name -eq $name) { return $layout }
        }
    }

    foreach ($hint in $ContainsHints) {
        for ($i = 1; $i -le $layouts.Count; $i++) {
            $layout = $layouts.Item($i)
            if ($layout.Name -like "*$hint*") { return $layout }
        }
    }

    return $null
}

function Get-LayoutSlotRule {
    param(
        $Mapping,
        [string]$LayoutName,
        [string]$SlotName
    )

    foreach ($rule in (Get-PropValue -Object $Mapping -Name 'layouts')) {
        $rx = Get-PropValue -Object $rule -Name 'match'
        if ($rx -and ($LayoutName -match $rx)) {
            $slots = Get-PropValue -Object $rule -Name 'slots'
            $slotRule = Get-PropValue -Object $slots -Name $SlotName
            if ($slotRule) { return $slotRule }
        }
    }

    $fallback = Get-PropValue -Object $Mapping -Name 'fallback_slots'
    return Get-PropValue -Object $fallback -Name $SlotName
}

function Test-ShapeSlotMatch {
    param(
        $Shape,
        $SlotRule
    )

    if ($Shape.Type -ne 14) { return $false }

    $phType = [int]$Shape.PlaceholderFormat.Type
    $name = [string]$Shape.Name
    $top = [double]$Shape.Top
    $height = [double]$Shape.Height
    $width = [double]$Shape.Width
    $left = [double]$Shape.Left

    $types = Get-PropValue -Object $SlotRule -Name 'placeholder_types'
    if ($types -and -not ($types -contains $phType)) { return $false }

    $nameRegex = Get-PropValue -Object $SlotRule -Name 'name_regex'
    if ($nameRegex -and -not ($name -match $nameRegex)) { return $false }

    $exclude = Get-PropValue -Object $SlotRule -Name 'exclude_name_regex'
    if ($exclude) {
        foreach ($rx in $exclude) {
            if ($name -match $rx) { return $false }
        }
    }

    $minTop = Get-PropValue -Object $SlotRule -Name 'min_top'
    if ($null -ne $minTop -and $top -lt [double]$minTop) { return $false }

    $maxTop = Get-PropValue -Object $SlotRule -Name 'max_top'
    if ($null -ne $maxTop -and $top -gt [double]$maxTop) { return $false }

    $minHeight = Get-PropValue -Object $SlotRule -Name 'min_height'
    if ($null -ne $minHeight -and $height -lt [double]$minHeight) { return $false }

    $maxHeight = Get-PropValue -Object $SlotRule -Name 'max_height'
    if ($null -ne $maxHeight -and $height -gt [double]$maxHeight) { return $false }

    $minWidth = Get-PropValue -Object $SlotRule -Name 'min_width'
    if ($null -ne $minWidth -and $width -lt [double]$minWidth) { return $false }

    $maxWidth = Get-PropValue -Object $SlotRule -Name 'max_width'
    if ($null -ne $maxWidth -and $width -gt [double]$maxWidth) { return $false }

    $minLeft = Get-PropValue -Object $SlotRule -Name 'min_left'
    if ($null -ne $minLeft -and $left -lt [double]$minLeft) { return $false }

    $maxLeft = Get-PropValue -Object $SlotRule -Name 'max_left'
    if ($null -ne $maxLeft -and $left -gt [double]$maxLeft) { return $false }

    return $true
}

function Select-SlotShape {
    param(
        $Slide,
        $Mapping,
        [string]$SlotName
    )

    $layoutName = [string]$Slide.CustomLayout.Name
    $slotRule = Get-LayoutSlotRule -Mapping $Mapping -LayoutName $layoutName -SlotName $SlotName
    if (-not $slotRule) { return $null }

    $candidates = @()
    for ($i = 1; $i -le $Slide.Shapes.Count; $i++) {
        $shape = $Slide.Shapes.Item($i)
        if (Test-ShapeSlotMatch -Shape $shape -SlotRule $slotRule) {
            $candidates += $shape
        }
    }
    if (-not $candidates -or $candidates.Count -eq 0) { return $null }

    $pick = Get-PropValue -Object $slotRule -Name 'pick'
    if (-not $pick) { $pick = 'topmost' }

    if ($pick -eq 'largest') {
        return ($candidates | Sort-Object { $_.Width * $_.Height }, Top, Left -Descending | Select-Object -First 1)
    }
    if ($pick -eq 'leftmost') {
        return ($candidates | Sort-Object Left, Top | Select-Object -First 1)
    }
    if ($pick -eq 'rightmost') {
        return ($candidates | Sort-Object Left, Top -Descending | Select-Object -First 1)
    }
    return ($candidates | Sort-Object Top, Left | Select-Object -First 1)
}

function Set-SlotText {
    param(
        $Slide,
        $Mapping,
        [string]$SlotName,
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $shape = Select-SlotShape -Slide $Slide -Mapping $Mapping -SlotName $SlotName
    if (-not $shape) { return $null }
    if ($shape.HasTextFrame -ne -1) { return $null }
    $shape.TextFrame.TextRange.Text = $Text
    return $shape.Name
}

function Convert-RowToStringArray {
    param(
        $Row,
        [string[]]$Headers
    )

    if ($null -eq $Row) { return @() }

    if ($Row -is [string]) { return @([string]$Row) }

    if ($Row -is [System.Array]) {
        return @($Row | ForEach-Object { if ($null -eq $_) { '' } else { [string]$_ } })
    }

    if ($Row -is [System.Collections.IList]) {
        return @($Row | ForEach-Object { if ($null -eq $_) { '' } else { [string]$_ } })
    }

    if ($Row.PSObject -and $Row.PSObject.Properties.Count -gt 0) {
        $props = @($Row.PSObject.Properties)
        if ($Headers -and $Headers.Count -gt 0) {
            $arr = @()
            foreach ($h in $Headers) {
                $val = Get-PropValue -Object $Row -Name $h
                $arr += $(if ($null -eq $val) { '' } else { [string]$val })
            }
            return $arr
        }
        return @($props | ForEach-Object { if ($null -eq $_.Value) { '' } else { [string]$_.Value } })
    }

    return @([string]$Row)
}

function Get-TableModelFromValue {
    param(
        $Value,
        [string]$ContentBaseDir
    )

    if ($null -eq $Value) { return $null }

    $headers = @()
    $rows = @()

    if ($Value -is [string]) {
        $csvPath = Resolve-ContentRelativePath -Path $Value -BaseDir $ContentBaseDir
        if (-not (Test-Path -LiteralPath $csvPath)) {
            Fail "Table source not found: $csvPath"
        }
        $csvRows = @(Import-Csv -LiteralPath $csvPath)
        if ($csvRows.Count -gt 0) {
            $headers = @($csvRows[0].PSObject.Properties.Name)
            foreach ($r in $csvRows) {
                $rows += ,(Convert-RowToStringArray -Row $r -Headers $headers)
            }
        }
    }
    elseif ($Value.PSObject -and $Value.PSObject.Properties.Count -gt 0) {
        $csvPathValue = Get-PropValue -Object $Value -Name 'csv_path'
        if ($csvPathValue) {
            $csvPath = Resolve-ContentRelativePath -Path ([string]$csvPathValue) -BaseDir $ContentBaseDir
            if (-not (Test-Path -LiteralPath $csvPath)) {
                Fail "Table csv_path not found: $csvPath"
            }
            $csvRows = @(Import-Csv -LiteralPath $csvPath)
            if ($csvRows.Count -gt 0) {
                $headers = @($csvRows[0].PSObject.Properties.Name)
                foreach ($r in $csvRows) {
                    $rows += ,(Convert-RowToStringArray -Row $r -Headers $headers)
                }
            }
        }
        else {
            $headers = @($(Get-PropValue -Object $Value -Name 'headers'))
            $rawRows = @($(Get-PropValue -Object $Value -Name 'rows'))
            if ((-not $headers -or $headers.Count -eq 0) -and $rawRows.Count -gt 0 -and $rawRows[0].PSObject) {
                $headers = @($rawRows[0].PSObject.Properties.Name)
            }
            foreach ($r in $rawRows) {
                $rows += ,(Convert-RowToStringArray -Row $r -Headers $headers)
            }
        }
    }
    else {
        return $null
    }

    if (($headers.Count -eq 0) -and ($rows.Count -eq 0)) { return $null }
    return [pscustomobject]@{
        headers = $headers
        rows = $rows
    }
}

function Set-SlotImage {
    param(
        $Slide,
        $Mapping,
        [string]$SlotName,
        $Value,
        [string]$ContentBaseDir
    )

    if ($null -eq $Value) { return $null }

    $imagePath = $null
    if ($Value -is [string]) {
        $imagePath = [string]$Value
    }
    elseif ($Value.PSObject) {
        $imagePath = [string](Get-PropValue -Object $Value -Name 'path')
    }

    if ([string]::IsNullOrWhiteSpace($imagePath)) { return $null }
    $resolved = Resolve-ContentRelativePath -Path $imagePath -BaseDir $ContentBaseDir
    if (-not (Test-Path -LiteralPath $resolved)) {
        Fail "Image source not found: $resolved"
    }

    $target = Select-SlotShape -Slide $Slide -Mapping $Mapping -SlotName $SlotName
    if (-not $target) { return $null }

    $left = [double]$target.Left
    $top = [double]$target.Top
    $width = [double]$target.Width
    $height = [double]$target.Height

    $pic = $Slide.Shapes.AddPicture($resolved, 0, -1, $left, $top, $width, $height)
    if ($target.Type -eq 14) {
        try { $target.Delete() } catch {}
    }
    return $pic.Name
}

function Set-SlotTable {
    param(
        $Slide,
        $Mapping,
        [string]$SlotName,
        $Value,
        [string]$ContentBaseDir
    )

    $model = Get-TableModelFromValue -Value $Value -ContentBaseDir $ContentBaseDir
    if (-not $model) { return $null }

    $target = Select-SlotShape -Slide $Slide -Mapping $Mapping -SlotName $SlotName
    if (-not $target) { return $null }

    $headers = @($model.headers)
    $rows = @($model.rows)

    $maxCols = 1
    if ($headers.Count -gt $maxCols) { $maxCols = $headers.Count }
    foreach ($r in $rows) {
        if ($r.Count -gt $maxCols) { $maxCols = $r.Count }
    }

    $hasHeader = ($headers.Count -gt 0)
    $rowCount = $rows.Count + $(if ($hasHeader) { 1 } else { 0 })
    if ($rowCount -lt 1) { $rowCount = 1 }

    $tblShape = $Slide.Shapes.AddTable($rowCount, $maxCols, [double]$target.Left, [double]$target.Top, [double]$target.Width, [double]$target.Height)
    $tbl = $tblShape.Table

    $rowIndex = 1
    if ($hasHeader) {
        for ($c = 1; $c -le $maxCols; $c++) {
            $text = ''
            if ($c -le $headers.Count) { $text = [string]$headers[$c - 1] }
            $cellText = $tbl.Cell($rowIndex, $c).Shape.TextFrame.TextRange
            $cellText.Text = $text
            $cellText.Font.Bold = -1
        }
        $rowIndex++
    }

    foreach ($r in $rows) {
        for ($c = 1; $c -le $maxCols; $c++) {
            $text = ''
            if ($c -le $r.Count) { $text = [string]$r[$c - 1] }
            $tbl.Cell($rowIndex, $c).Shape.TextFrame.TextRange.Text = $text
        }
        $rowIndex++
    }

    if ($target.Type -eq 14) {
        try { $target.Delete() } catch {}
    }
    return $tblShape.Name
}

function Set-SlotValue {
    param(
        $Slide,
        $Mapping,
        [string]$SlotName,
        $Value,
        [string]$ContentBaseDir
    )

    if ($SlotName -eq 'image') {
        return Set-SlotImage -Slide $Slide -Mapping $Mapping -SlotName $SlotName -Value $Value -ContentBaseDir $ContentBaseDir
    }
    if ($SlotName -eq 'table') {
        return Set-SlotTable -Slide $Slide -Mapping $Mapping -SlotName $SlotName -Value $Value -ContentBaseDir $ContentBaseDir
    }
    return Set-SlotText -Slide $Slide -Mapping $Mapping -SlotName $SlotName -Text ([string]$Value)
}

foreach ($p in @($TemplatePath, $MappingPath, $ContentPath)) {
    if (-not (Test-Path -LiteralPath $p)) { Fail "Not found: $p" }
}

$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$mapping = Get-Content -LiteralPath $MappingPath -Raw -Encoding UTF8 | ConvertFrom-Json
$content = Get-Content -LiteralPath $ContentPath -Raw -Encoding UTF8 | ConvertFrom-Json
$contentBaseDir = Split-Path -Parent (Resolve-Path -LiteralPath $ContentPath).ProviderPath

$pp = $null
$pres = $null
try {
    Info "COM: instantiate template -> $OutputPath"
    $pp = New-Object -ComObject PowerPoint.Application
    $pres = $pp.Presentations.Open((Resolve-Path -LiteralPath $TemplatePath).ProviderPath, 0, -1, 0)
    if (Test-Path -LiteralPath $OutputPath) { Remove-Item -LiteralPath $OutputPath -Force }
    $pres.SaveAs($OutputPath, 24)

    $baseline = $pres.Slides.Count
    $index = 0
    $audit = @()
    foreach ($slideSpec in $content.slides) {
        $index++
        $layoutNames = @($slideSpec.layout_names)
        $layoutHints = @($slideSpec.layout_hints)
        $layout = Get-CustomLayout -Presentation $pres -PreferredNames $layoutNames -ContainsHints $layoutHints
        if (-not $layout) {
            Fail ("Layout not found for slide {0}. names={1}" -f $index, ($layoutNames -join ', '))
        }

        $slide = $pres.Slides.AddSlide($index, $layout)
        $slotAudit = [ordered]@{
            slide = $index
            layout = $layout.Name
        }
        foreach ($slotProp in $slideSpec.slots.PSObject.Properties) {
            $slotName = [string]$slotProp.Name
            $slotValue = $slotProp.Value
            $shapeName = Set-SlotValue -Slide $slide -Mapping $mapping -SlotName $slotName -Value $slotValue -ContentBaseDir $contentBaseDir
            $slotAudit[$slotName] = $(if ($shapeName) { $shapeName } else { $null })
        }
        $audit += [pscustomobject]$slotAudit
    }

    $pres.Save()

    @{
        success = $true
        output_path = (Resolve-Path -LiteralPath $OutputPath).ProviderPath
        baseline_slides = $baseline
        inserted_front = $content.slides.Count
        total_slides = $pres.Slides.Count
        mapping_path = (Resolve-Path -LiteralPath $MappingPath).ProviderPath
        content_path = (Resolve-Path -LiteralPath $ContentPath).ProviderPath
        slot_audit = $audit
    } | ConvertTo-Json -Depth 8
}
finally {
    if ($pres) { $pres.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($pres) }
    if ($pp) { $pp.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($pp) }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
