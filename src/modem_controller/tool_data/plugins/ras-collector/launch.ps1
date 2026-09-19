#requires -version 5.1
# Standalone plugin interface. Opening this window never collects host data.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Windows RAS diagnostics'
$form.Size = New-Object System.Drawing.Size(580, 515)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$layout = New-Object System.Windows.Forms.FlowLayoutPanel
$layout.Dock = 'Fill'
$layout.FlowDirection = 'TopDown'
$layout.WrapContents = $false
$layout.Padding = New-Object System.Windows.Forms.Padding(12)
$form.Controls.Add($layout)

$notice = New-Object System.Windows.Forms.Label
$notice.Text = 'Choose the evidence to collect. Nothing changes on the modem or host. Review the report before sharing.'
$notice.Size = New-Object System.Drawing.Size(530, 35)
$layout.Controls.Add($notice)
$choices = [ordered]@{}
foreach ($item in @(
    @('modems', 'Installed modem summary'),
    @('ports', 'Serial port summary'),
    @('network', 'Adapter status, without addresses'),
    @('ras', 'RAS status availability, without connection names'),
    @('phonebook', 'Current-user phonebook device fields'),
    @('events', 'RasClient event IDs, levels and times')
)) {
    $box = New-Object System.Windows.Forms.CheckBox
    $box.Text = $item[1]
    $box.AutoSize = $true
    $choices[$item[0]] = $box
    $layout.Controls.Add($box)
}
$hoursLabel = New-Object System.Windows.Forms.Label
$hoursLabel.Text = 'Event window (hours)'
$hoursLabel.AutoSize = $true
$layout.Controls.Add($hoursLabel)
$hours = New-Object System.Windows.Forms.NumericUpDown
$hours.Minimum = 1
$hours.Maximum = 168
$hours.Value = 24
$layout.Controls.Add($hours)
$pathLabel = New-Object System.Windows.Forms.Label
$pathLabel.Text = 'New output directory'
$pathLabel.AutoSize = $true
$layout.Controls.Add($pathLabel)
$destination = New-Object System.Windows.Forms.TextBox
$destination.Width = 520
$destination.Text = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('ras-report-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
$layout.Controls.Add($destination)
$browse = New-Object System.Windows.Forms.Button
$browse.Text = 'Choose parent...'
$browse.AutoSize = $true
$browse.Add_Click({
    $picker = New-Object System.Windows.Forms.FolderBrowserDialog
    try {
        if ($picker.ShowDialog() -eq 'OK') {
            $destination.Text = Join-Path $picker.SelectedPath ('ras-report-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss'))
        }
    } finally { $picker.Dispose() }
})
$layout.Controls.Add($browse)
$consent = New-Object System.Windows.Forms.CheckBox
$consent.Text = 'I consent to the selected local collection and report creation'
$consent.AutoSize = $true
$layout.Controls.Add($consent)
$run = New-Object System.Windows.Forms.Button
$run.Text = 'Collect selected'
$run.AutoSize = $true
$layout.Controls.Add($run)
$status = New-Object System.Windows.Forms.Label
$status.Size = New-Object System.Drawing.Size(530, 45)
$layout.Controls.Add($status)
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 200
$script:job = $null
$script:pending = $null

$run.Add_Click({
    $selected = @($choices.Keys | Where-Object { $choices[$_].Checked })
    if (-not $consent.Checked -or $selected.Count -eq 0) {
        $status.Text = 'Select at least one source and consent before collecting.'
        return
    }
    if (-not [System.IO.Path]::IsPathRooted($destination.Text) -or $destination.Text.StartsWith('\\') -or (Test-Path -LiteralPath $destination.Text)) {
        $status.Text = 'Choose a new absolute local output directory.'
        return
    }
    try {
        $script:job = [PowerShell]::Create()
        [void]$script:job.AddCommand((Join-Path $PSScriptRoot 'ras-collect.ps1')).AddParameter('OutputDirectory', $destination.Text).AddParameter('Collectors', ($selected -join ',')).AddParameter('Hours', [int]$hours.Value).AddParameter('Consent', $true)
        $script:pending = $script:job.BeginInvoke()
        $script:started = [DateTime]::UtcNow
        foreach ($control in $layout.Controls) { $control.Enabled = $false }
        $status.Enabled = $true
        $status.Text = 'Collecting selected evidence. Close this window to cancel.'
        $timer.Start()
    } catch {
        if ($script:job) { $script:job.Dispose(); $script:job = $null }
        $status.Text = 'Collection could not start: ' + $_.Exception.Message
    }
})
$timer.Add_Tick({
    if (-not $script:pending.IsCompleted -and ([DateTime]::UtcNow - $script:started).TotalSeconds -lt 60) { return }
    $timer.Stop()
    try {
        if (-not $script:pending.IsCompleted) {
            $script:job.Stop()
            $status.Text = 'Collection timed out. Any saved report is partial.'
        } else {
            [void]$script:job.EndInvoke($script:pending)
            $status.Text = if ($script:job.HadErrors) { 'Collection failed; inspect any partial report in the selected folder.' } else { 'Report saved in the selected folder. Review before sharing.' }
        }
    } catch { $status.Text = 'Collection failed; inspect any partial report in the selected folder.' }
    finally {
        $script:job.Dispose()
        $script:job = $null
        foreach ($control in $layout.Controls) { $control.Enabled = $true }
    }
})
$form.Add_FormClosing({
    $timer.Stop()
    if ($script:job) { $script:job.Stop(); $script:job.Dispose(); $script:job = $null }
})
try { [void]$form.ShowDialog() }
finally { $timer.Dispose(); $form.Dispose() }
