"""Pydantic models for everything saved under runs/. Numbers shown anywhere come from these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RunKind = Literal["b0", "b1", "b2", "unpinned"]


class SuiteCounts(BaseModel):
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped


class Failure(BaseModel):
    test: str
    trace_head: str = ""


class ExploitResult(BaseModel):
    cve: str
    django_version: str
    blocked: bool
    evidence: str = ""
    outcome: Literal["vulnerable", "blocked", "error", "timeout", "skipped"] = "error"
    benign_control_passed: bool = False
    probe_sha256: str = ""


class VerifyReport(BaseModel):
    """Strict JSON the managed agent must return (SPEC §7)."""

    python_version: str = ""
    django_version: str = ""
    test_command: str = ""
    suite: SuiteCounts = Field(default_factory=SuiteCounts)
    failures: list[Failure] = Field(default_factory=list)
    check: list[str] = Field(default_factory=list, description="manage.py check issues")
    deprecation_warnings: int | None = None
    exploits: list[ExploitResult] = Field(default_factory=list)
    install_ok: bool = False
    notes: str = ""
    tests_exit_code: int | None = None
    checks_exit_code: int | None = None
    source_commit: str = ""
    patch_sha256: str = ""
    # Set only by an independent artifact verifier, never by model output.
    artifacts_verified: bool = False
    evidence_source: Literal["agent_summary", "local_fixture", "sandbox_artifacts"] = (
        "agent_summary"
    )


class PlanItem(BaseModel):
    file: str
    line: int | None = None
    rule: str
    fix: str


class Plan(BaseModel):
    items: list[PlanItem] = Field(default_factory=list)


class Iteration(BaseModel):
    n: int
    interaction_id: str | None = None
    environment_id: str | None = None
    files_changed: int = 0
    report: VerifyReport
    wall_seconds: float = 0.0


class RunSummary(BaseModel):
    run_id: str
    kind: RunKind
    repo_url: str
    target_django: str
    started_at: str
    iterations: list[Iteration] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    wall_seconds: float | None = None
    approved: bool = False
    pr_url: str | None = None
    source_commit: str = ""
    baseline_report: VerifyReport | None = None
    review_blockers: list[str] = Field(default_factory=list)

    @property
    def final(self) -> VerifyReport | None:
        return self.iterations[-1].report if self.iterations else None
