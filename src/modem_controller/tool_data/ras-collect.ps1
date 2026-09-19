#requires -version 5.1
<#
Bounded opt-in evidence collector. Never changes host or modem settings.
FixtureDirectory is an offline test adapter; it bypasses every host query.
#>
param(
    [string]$OutputDirectory,
    [string]$Collectors = '',
    [ValidateRange(1,168)][int]$Hours = 24,
    [switch]$Consent,
    [string]$PhonebookPath = '',
    [string]$FixtureDirectory = ''
)
$ErrorActionPreference = 'Stop'

function Protect-Text([string]$Value) {
    if ($Value -match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$') { return $Value }
    $Value = [regex]::Replace($Value, '(?i)(password|passwd|secret|token|pin|puk|username|user|phone(number)?|server(address)?)\s*[:=]\s*[^\r\n,;]+', '$1=<redacted>')
    $Value = [regex]::Replace($Value, '(?i)AT\+(CPIN|CPWD|CLCK)\s*=.*', '<credential command omitted>')
    $Value = [regex]::Replace($Value, '\b\d{1,3}(\.\d{1,3}){3}\b', '<ip redacted>')
    $Value = [regex]::Replace($Value, '(?<!\w)\+?\d[\d ()-]{5,}\d(?!\w)', '<number redacted>')
    $Value = [regex]::Replace($Value, '[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<email redacted>')
    return $Value
}

function Protect-Data($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) { return (Protect-Text $Value) }
    if ($Value -is [System.Collections.IDictionary]) {
        $clean = [ordered]@{}
        foreach ($key in $Value.Keys) {
            if ($key -match '(?i)password|secret|token|pin|puk|username|phone|serveraddress|macaddress|ipaddress') { $clean[$key] = '<redacted>' }
            else { $clean[$key] = Protect-Data $Value[$key] }
        }
        return $clean
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $map = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) { $map[$property.Name] = $property.Value }
        return (Protect-Data $map)
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        if (@($Value).Count -gt 100) { $script:DataTruncated = $true }
        return ,@($Value | Select-Object -First 100 | ForEach-Object { Protect-Data $_ })
    }
    return $Value
}

function Read-SelectedCollector([string]$Name) {
    if ($FixtureDirectory) {
        $fixture = Join-Path $FixtureDirectory ($Name + '.json')
        if (-not (Test-Path -LiteralPath $fixture -PathType Leaf)) { return @{status='unsupported'; data=$null; reason='Fixture unavailable'} }
        if ((Get-Item -LiteralPath $fixture).Length -gt 1048576) { throw 'Fixture exceeds 1 MiB' }
        return (Get-Content -LiteralPath $fixture -Raw | ConvertFrom-Json)
    }
    switch ($Name) {
        'modems' { $data = @(Get-CimInstance Win32_POTSModem | Select-Object -First 101 Name,Status,AttachedTo,DeviceType) }
        'ports' { $data = @(Get-CimInstance Win32_SerialPort | Select-Object -First 101 DeviceID,Name,Status) }
        'network' { $data = @(Get-NetAdapter | Select-Object -First 101 InterfaceDescription,Status,LinkSpeed) }
        'ras' {
            $command = Get-Command rasdial.exe -ErrorAction Stop
            $lines = @(& $command.Source 2>&1 | Select-Object -First 100)
            if ($LASTEXITCODE -ne 0) { throw 'RAS status command failed' }
            # Connection names may be identifying, so retain only availability/count.
            $data = @{status_command='completed'; line_count=$lines.Count; notice='Connection names omitted; this count is not a connection count.'}
        }
        'phonebook' {
            $selected = $PhonebookPath
            if (-not $selected) { $selected = Join-Path $env:APPDATA 'Microsoft\Network\Connections\Pbk\rasphone.pbk' }
            if (-not (Test-Path -LiteralPath $selected -PathType Leaf)) { throw 'Selected current-user phonebook unavailable' }
            if ((Get-Item -LiteralPath $selected).Length -gt 1048576) { throw 'Phonebook exceeds 1 MiB' }
            $lines = Get-Content -LiteralPath $selected | Where-Object { $_ -match '^(Type|Device|DeviceType)=' } | Select-Object -First 101
            $data = @($lines)
        }
        'events' {
            $filter = @{LogName='Application'; ProviderName='RasClient'; StartTime=(Get-Date).AddHours(-$Hours)}
            $data = @(Get-WinEvent -FilterHashtable $filter -MaxEvents 101 -ErrorAction Stop | ForEach-Object {
                @{id=$_.Id; level=$_.LevelDisplayName; time=$_.TimeCreated.ToUniversalTime().ToString('o')}
            })
        }
        default { throw 'Unknown collector' }
    }
    return @{status='ok'; data=$data; reason='Selected read-only host observation'}
}

function Save-Report($Report, [string]$Directory) {
    $json = $Report | ConvertTo-Json -Depth 15
    if ([System.Text.Encoding]::UTF8.GetByteCount($json) -gt 1048576) { throw 'Report exceeds 1 MiB' }
    $destination = Join-Path $Directory 'ras-report.json'
    $temporary = Join-Path $Directory 'ras-report.partial.json'
    [System.IO.File]::WriteAllText($temporary, $json, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $destination) { [System.IO.File]::Replace($temporary, $destination, [NullString]::Value) }
    else { [System.IO.File]::Move($temporary, $destination) }
}

if (-not $Consent) { throw 'Explicit collection consent is required' }
if (-not $OutputDirectory -or -not [System.IO.Path]::IsPathRooted($OutputDirectory) -or $OutputDirectory.StartsWith('\\')) { throw 'Choose an absolute local output directory' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new output directory; existing data is never replaced' }
$selectedCollectors = @($Collectors.Split(',') | Where-Object { $_ } | Select-Object -Unique)
if ($selectedCollectors.Count -eq 0) { throw 'Select at least one collector' }
foreach ($name in $selectedCollectors) { if ($name -notin @('modems','ports','network','ras','phonebook','events')) { throw 'Unsupported collector' } }
[void][System.IO.Directory]::CreateDirectory($OutputDirectory)
$report = [ordered]@{schema_version=1; generated_utc=[DateTime]::UtcNow.ToString('o'); hours=$Hours; partial=$true; results=@(); notice='Selected redacted observations; no dialing or settings changes. User review is required before sharing.'}
Save-Report $report $OutputDirectory
foreach ($name in $selectedCollectors) {
    try {
        $script:DataTruncated = $false
        $item = Read-SelectedCollector $name
        if ($item.status -notin @('ok','unsupported','error')) { throw 'Invalid collector status' }
        $result = @{collector=$name; status=$item.status; data=(Protect-Data $item.data); reason=(Protect-Text $item.reason)}
        if ($script:DataTruncated) { $result.status='error'; $result.reason='Rows truncated to the first 100; partial evidence' }
        $encoded = $result | ConvertTo-Json -Depth 12
        if ([System.Text.Encoding]::UTF8.GetByteCount($encoded) -gt 100000) { $result.data=@(); $result.status='error'; $result.reason='Collector output exceeds 100000 bytes' }
    } catch {
        $status = if ($_.Exception -is [System.Management.Automation.CommandNotFoundException]) { 'unsupported' } else { 'error' }
        $result = @{collector=$name; status=$status; data=@(); reason='Collector unavailable or access denied; no repair attempted'}
    }
    $report.results += $result
    Save-Report $report $OutputDirectory
}
$report.partial = @($report.results | Where-Object { $_.status -ne 'ok' }).Count -gt 0
Save-Report $report $OutputDirectory
Write-Output ('Saved selected collection: ' + (Join-Path $OutputDirectory 'ras-report.json'))
