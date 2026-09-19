"""Run the standalone form with a synthetic collector, never host queries."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Forms plugin")
def test_ras_plugin_requires_scope_and_consent_then_passes_selected_arguments(tmp_path):
    source = (
        Path(__file__).parents[2]
        / "src/modem_controller/tool_data/plugins/ras-collector/launch.ps1"
    )
    collector = tmp_path / "ras-collect.ps1"
    collector.write_text(
        "param($OutputDirectory, $Collectors, $Hours, [switch]$Consent)\n"
        "if ($Collectors -ne 'ports' -or $Hours -ne 24 -or -not $Consent) {"
        " throw 'Unexpected scope' }\n"
        "[void][IO.Directory]::CreateDirectory($OutputDirectory)\n"
        "[IO.File]::WriteAllText((Join-Path $OutputDirectory 'fixture.txt'), 'ports')\n"
    )
    text = source.read_text()
    marker = "try { [void]$form.ShowDialog() }"
    assert marker in text
    setup = r"""
$form.Opacity = 0
$script:failure = ''
$form.Add_Shown({
    try {
        $destination.Text = Join-Path $PSScriptRoot 'output'
        $run.PerformClick()
        if ($script:job -or (Test-Path -LiteralPath $destination.Text)) {
            throw 'Started without scope'
        }
        $choices['ports'].Checked = $true
        $run.PerformClick()
        if ($script:job) { throw 'Started without consent' }
        $consent.Checked = $true
        $run.PerformClick()
        if (-not $script:job) { throw ('Did not start: ' + $status.Text) }
    } catch { $script:failure = $_.Exception.Message; $form.Close() }
})
$testTimer = New-Object System.Windows.Forms.Timer
$testTimer.Interval = 100
$testTimer.Add_Tick({
    if (-not $script:job) { $testTimer.Stop(); $form.Close() }
})
$testTimer.Start()
"""
    text = text.replace(marker, setup + "\n" + marker)
    text += "\n$testTimer.Dispose()\nif ($script:failure) { throw $script:failure }\n"
    launcher = tmp_path / "launch.ps1"
    launcher.write_text(text)
    powershell = (
        Path(os.environ.get("SystemRoot", "C:/Windows"))
        / "System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    result = subprocess.run(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-File",
            str(launcher),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output/fixture.txt").read_text() == "ports"
