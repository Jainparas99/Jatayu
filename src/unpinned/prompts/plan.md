You are upgrading a {framework} project ({language}) from {from_version} to {to_version}. Below are (1) the official {framework} upgrade notes for every version in between (backwards-incompatible changes and removed features) and (2) the ENTIRE project as FILE blocks.

List every place in the project that must change for it to run on {framework} {to_version} with no deprecation warnings from the project's own code. Be exhaustive: settings, imports, removed APIs, changed defaults, template tags, test utilities, requirements pins. Cross-check usages across files.

Reply with ONLY JSON: {{"items": [{{"file": str, "line": int|null, "rule": "release-note rule, quoted briefly", "fix": str}}]}}

=== RELEASE NOTES ===
{release_notes}

=== PROJECT ===
{bundle}
