# Portable plugins

Choose **Plugins...**, select a plugin and click **Start plugin**. The application
releases its serial connection before opening the list. Opening the list, selecting
an entry or starting the modem application never executes a plugin. Each plugin
opens its own interface and owns its options, output, progress and lifetime.
Closing the launcher or modem application does not stop an already started plugin.

Place each plugin in its own folder beside the portable executable:

```text
plugins/
  my-tool/
    plugin.json
    MyTool.exe
```

The configuration contains only a name, program and optional argument list:

```json
{
  "name": "My diagnostic tool",
  "program": "MyTool.exe",
  "arguments": ["settings/default.json"]
}
```

Only child folders with a valid configuration appear. Relative programs and
argument paths use that plugin's folder; arguments remain separate literal values.
The launcher does not compose a shell command. Missing programs and failed starts
are shown in the launcher. An empty or removed portable `plugins` folder stays
empty; source checkouts can use their bundled plugin resources without copying.

An executable starts directly. A `.ps1` entry starts with the installed Windows
PowerShell runtime, `-NoProfile -STA -File`, without changing execution policy or
installing anything. The bundled RAS plugin uses this route. Other scripting
runtimes can be selected as the program with the script in the argument list.

The modem application never requests administrator rights. A plugin may request
UAC itself when its own operation requires it. Plugins are ordinary local programs;
install only plugins you trust, keep private inputs out of `plugin.json`, and close
serial connections inside a plugin before reconnecting the modem application.
The older reviewed process-runner API remains available internally; its review,
output capture and cancellation UI is no longer part of the desktop launcher.
