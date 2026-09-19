# Optional Windows RAS diagnostics plugin

Open **Plugins...**, select **Windows RAS diagnostics**, then **Start plugin**.
The standalone plugin asks which sources to collect, the 1-168 hour event window,
a new output directory and explicit consent. Click **Collect selected** to begin.
Opening either window never collects data. No source is preselected. Normal modem
use requires neither this plugin nor administrator rights. The plugin and host do
not install runtimes, elevate or change execution policy.

The collector reads only selected modem, port, adapter, RAS status, current-user
phonebook or RasClient event summaries. It never searches other users' profiles,
dials/disconnects, enables logging, changes registry/services or installs drivers.
Phonebooks include only Type/Device/DeviceType fields; event messages, connection
names and network addresses are omitted. RAS status records command availability
and output line count, not an active-connection count.

The collection runs asynchronously in the plugin. Closing its window cancels the
collection; the launcher can be closed independently. A 60-second deadline stops
the collection. Results are saved atomically after each source; interruption can
leave a partial report or temporary partial file. Existing output directories are
refused. Choose a new destination for another run.

Rows are limited to 100 per collector, serialized results to 100,000 bytes each,
and the report to 1 MiB. Missing commands, access-denied or unknown sources remain
partial, with no repair or fallback collection. Redaction removes common credential,
phone/IP/email patterns; review device descriptions before sharing. Redaction is
not an anonymity guarantee.

The portable folder is `plugins/ras-collector`, containing `plugin.json`, the
standalone `launch.ps1` interface and `ras-collect.ps1`. The configuration contains
no personal paths or collection choices. The collector's `-FixtureDirectory`
adapter reads only synthetic selected JSON fixtures and bypasses all host queries,
including missing fixtures. Such tests establish bounds and error handling, not
actual RAS diagnosis. Actual host collection and acceptance remain separate.
