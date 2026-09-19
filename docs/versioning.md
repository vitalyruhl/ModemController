# Product version and build identity

Root `version.json` is the only authored semantic-version source. Setuptools,
installed/frozen resources, the desktop title, console `--version`, reports,
Windows executable metadata and portable archive names derive from it. Missing,
malformed or conflicting packaged build metadata fails explicitly.

The approved initial implementation interval remains **2.0.0** throughout all
plan points, including Tools/RAS. User HIL follows that implementation. Subsequent
compatible fixes increment patch; new compatible capabilities increment minor.
Major changes need an explicit decision. No tag or public release is implicit.

The desktop title shows only the product version. The console version output,
archive name and `build-info.json` retain source identity for troubleshooting.
`build-info.json` also records the dependency-lock SHA-256 and
Python build version. A dirty build is for development, not an exact committed
acceptance candidate. Source archives carry the same derived provenance; build
outputs never rewrite `version.json`.

The local build cache includes `version.json` so an intentional version change
refreshes installed metadata with the normal frozen sync. This uses uv's
[dynamic metadata cache keys](https://docs.astral.sh/uv/concepts/cache/#dynamic-metadata).

After a version change run `uv lock` and `uv sync --frozen` intentionally, then
validate the affected code and `uv build`. Build the portable candidate from the
identified clean source. Retain prior artifacts and their evidence rather than
renaming them to imply a different tested version.
