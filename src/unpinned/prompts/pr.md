A human has APPROVED this change. You may now push and open a pull request, and only this:

1. `git clone {fork_url} repo && cd repo && git checkout -b {branch}`
2. Apply the file changes below exactly (FILE blocks replace whole files; DELETE removes).
3. `git add -A && git commit -m "Upgrade to Django {to_version} (Jatayu)"`
4. `git push origin {branch}` using the GitHub credential provided by the environment.
5. Open a pull request on {fork_owner}/{repo_name} from `{branch}` into the default branch with this body:

{pr_body}

Reply with ONLY JSON: {{"pr_url": str, "branch": str, "commit": str}}

{file_changes}
