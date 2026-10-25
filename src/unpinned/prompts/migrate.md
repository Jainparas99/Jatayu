You are upgrading a {framework} project ({language}) from {from_version} to {to_version} in ONE response. You have the official release notes, the plan of required changes, and the ENTIRE project.

Rules:
- Output every file that must change, IN FULL (complete new content, not a diff), using exactly this format and nothing else:
<<<FILE path/relative/to/repo.py>>>
...complete new file content...
<<<END FILE>>>
- To delete a file: <<<DELETE path/to/file.py>>>
- End with:
<<<SUMMARY>>>
- path: one-line reason (cite the release-note rule)
<<<END SUMMARY>>>
- New files must be listed in SUMMARY.
- Update the dependency manifest so the project pins {framework} {to_version}.
- Keep behaviour identical. Keep changes consistent across files (a renamed setting must be renamed everywhere it is used).
- Never touch .git/, .github/workflows/, or secrets files.

=== RELEASE NOTES ===
{release_notes}

=== PLAN ===
{plan}

=== PROJECT ===
{bundle}
