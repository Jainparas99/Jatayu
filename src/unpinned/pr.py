"""APPROVE → push a branch + open a PR on the fork, via the managed agent (SPEC §4 step 6). [CP4]

This is the ONLY code path allowed to cause an external side effect (AGENTS.md invariant 3).
"""

from __future__ import annotations

from .config import settings
from .review import review_state


class NotApproved(PermissionError):
    pass


def open_pr(run_id: str, *, approved_by_human: bool, patch_sha256: str = "") -> str:
    if not approved_by_human:
        raise NotApproved("PRs are opened only from the /approve handler after a human click")
    review = review_state(run_id)
    if not review["ready_for_review"]:
        raise NotApproved("Verification is incomplete: " + "; ".join(review["blockers"]))
    if not patch_sha256 or patch_sha256 != review["patch_sha256"]:
        raise NotApproved("Approval must refer to the current reviewed patch digest.")
    s = settings()
    if not s.fork_owner:
        raise RuntimeError("set JATAYU_FORK_OWNER in .env; PRs go only to your fork")
    raise NotImplementedError(
        "CP4: gemini.register_github_token(s.github_token) once, then gemini.run_agent("
        "prompts.load('pr', ...)) with the GitHub allowlist; save pr_url into summary.json"
    )
