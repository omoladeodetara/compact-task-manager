#Requires -Version 5.1
function Read-CompactConfig {
    param([string]$Path)
    $result = [pscustomobject]@{ X = $null; Y = $null; Height = 540; AlwaysOnTop = $true }
    if (Test-Path -LiteralPath $Path) {
        $inputConfig = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
        foreach ($name in @('X', 'Y', 'Height', 'AlwaysOnTop')) {
            if ($inputConfig.PSObject.Properties.Name -contains $name) { $result.$name = $inputConfig.$name }
        }
    }
    if (($null -eq $result.X) -ne ($null -eq $result.Y)) { throw 'Set both X and Y, or leave both null.' }
    foreach ($name in @('X', 'Y', 'Height')) {
        $value = $result.$name
        if ($null -eq $value -and $name -ne 'Height') { continue }
        if ($null -eq $value -or $value -is [bool] -or $value -is [string] -or $value -is [array] -or
            $value -notmatch '^-?\d+$' -or [double]$value -lt -100000 -or [double]$value -gt 100000) {
            throw "$name must be an integer between -100000 and 100000."
        }
        $result.$name = [int]$value
    }
    if ($result.Height -lt 200 -or $result.Height -gt 4000) { throw 'Height must be between 200 and 4000.' }
    if ($result.AlwaysOnTop -isnot [bool]) { throw 'AlwaysOnTop must be true or false.' }
    return $result
}

function Get-CompactPlacement {
    param($Config, $Area, [int]$Width)
    $widthValue = [Math]::Min($Width, $Area.Width)
    $heightValue = [Math]::Min($Config.Height, $Area.Height)
    $desiredX = $Config.X; $desiredY = $Config.Y
    if ($null -eq $desiredX) { $desiredX = $Area.Right - $widthValue - 16; $desiredY = $Area.Top + 16 }
    return [pscustomobject]@{
        X = [Math]::Max($Area.Left, [Math]::Min($desiredX, $Area.Right - $widthValue))
        Y = [Math]::Max($Area.Top, [Math]::Min($desiredY, $Area.Bottom - $heightValue))
        Width = $widthValue
        Height = $heightValue
    }
}
