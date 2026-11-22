"""Evidence mappers for the Jenkins CI/CD investigation tools."""

from __future__ import annotations

from typing import Any

from core.domain.types.evidence import record_evidence_entry

_FAILED_BUILD_STATUSES = frozenset({"FAILURE"})
_FAILED_JOB_STATUSES = frozenset({"FAILURE"})
_FAILED_STAGE_STATUSES = frozenset({"FAILED"})
#: A build that completed but whose tests failed. Not a hard failure, yet a
#: summary that omits it reads as healthy, so it is cited beside the failures.
_UNSTABLE_STATUS = "UNSTABLE"


def _count_with_status(items: list[dict[str, Any]], statuses: frozenset[str] | str) -> int:
    wanted = frozenset({statuses}) if isinstance(statuses, str) else statuses
    return sum(1 for item in items if str(item.get("status", "")).upper() in wanted)


def _unstable_suffix(items: list[dict[str, Any]], truncated: bool) -> str:
    """Return ``", N unstable"`` when any item is unstable, else an empty string."""
    unstable = _count_with_status(items, _UNSTABLE_STATUS)
    if not unstable:
        return ""
    return f", {unstable}+ unstable" if truncated else f", {unstable} unstable"


#: The client's own hard ceiling on how many builds it will ever fetch or
#: return in one call (``max(1, min(limit, 50))`` for the unfiltered path).
#: A caller-requested ``limit`` above this is never actually honored, so the
#: real ceiling to compare against is always ``min(limit, _JENKINS_BUILD_FETCH_CAP)``.
_JENKINS_BUILD_FETCH_CAP = 50


def map_list_jenkins_builds(
    evidence: dict[str, Any], output: dict[str, Any], tool_input: dict[str, Any]
) -> None:
    """Cite the build count and how many failed, qualifying page-capped totals.

    ``total`` mirrors ``len(builds)`` after the client's own limit slice, so
    a returned count at that ceiling may understate the true number of
    builds -- use the "N+" convention against ``min(limit, 50)``, the
    client's real ceiling (a caller-requested ``limit`` above 50 is never
    actually honored).

    When a ``status`` filter is set, the client always scans only the 50
    *most recent* builds before filtering -- regardless of ``limit`` -- and
    doesn't expose whether history beyond that window also matches. The
    result can never be proven exact in that case, so it's always qualified
    with "+"; citing the filter instead of a derived failed count too, since
    every returned build already matches it (a filtered "0 failed" would
    misrepresent unfiltered reality).
    """
    if not output.get("available"):
        return
    builds = output.get("builds") or []
    if not builds:
        return
    total = output.get("total", len(builds))
    status_filter = tool_input.get("status")
    if status_filter:
        summary = f"{total}+ build(s) with status '{status_filter}'"
    else:
        requested_limit = tool_input.get("limit", 10)
        effective_limit = min(max(requested_limit, 1), _JENKINS_BUILD_FETCH_CAP)
        truncated = total >= effective_limit
        total_label = f"{total}+" if truncated else str(total)
        failed = _count_with_status(builds, _FAILED_BUILD_STATUSES)
        failed_label = f"{failed}+" if truncated else str(failed)
        summary = f"{total_label} build(s), {failed_label} failed"
        summary += _unstable_suffix(builds, truncated)
    job = output.get("job")
    if job:
        summary += f" for '{job}'"
    record_evidence_entry(
        evidence,
        source="list_jenkins_builds",
        label="Jenkins Builds",
        summary=summary,
    )


def map_get_jenkins_build_log(
    evidence: dict[str, Any], output: dict[str, Any], _tool_input: dict[str, Any]
) -> None:
    """Cite the console log length, using the client's own tail-truncation flag."""
    if not output.get("available"):
        return
    log = output.get("log") or ""
    if not log:
        return
    parts = [f"{len(log)} char(s) of console log"]
    if output.get("truncated"):
        parts.append("truncated to tail")
    job = output.get("job")
    build_number = output.get("build_number")
    if job and build_number is not None:
        parts.append(f"for '{job}' #{build_number}")
    record_evidence_entry(
        evidence,
        source="get_jenkins_build_log",
        label="Jenkins Build Log",
        summary=", ".join(parts),
    )


def map_get_jenkins_pipeline_stages(
    evidence: dict[str, Any], output: dict[str, Any], _tool_input: dict[str, Any]
) -> None:
    """Cite the stage count and how many failed.

    Freestyle jobs (``is_pipeline`` False) have no stages -- that's an
    expected, unremarkable outcome, not a finding worth citing.
    """
    if not output.get("available") or not output.get("is_pipeline"):
        return
    stages = output.get("stages") or []
    if not stages:
        return
    failed = _count_with_status(stages, _FAILED_STAGE_STATUSES)
    summary = f"{len(stages)} stage(s), {failed} failed"
    status = output.get("status")
    if status:
        summary += f" (build status: {status})"
    job = output.get("job")
    build_number = output.get("build_number")
    if job and build_number is not None:
        summary += f" for '{job}' #{build_number}"
    record_evidence_entry(
        evidence,
        source="get_jenkins_pipeline_stages",
        label="Jenkins Pipeline Stages",
        summary=summary,
    )


def map_list_jenkins_jobs(
    evidence: dict[str, Any], output: dict[str, Any], _tool_input: dict[str, Any]
) -> None:
    """Cite the job count and how many are currently failing.

    ``truncated`` is the client's own explicit signal (folder-depth or job
    cap dropped jobs), not an inferred heuristic. A depth-limited scan whose
    only matches lie beyond the boundary returns an empty ``jobs`` list with
    ``truncated`` still set -- that incompleteness is itself worth citing, so
    only an empty *and* untruncated result (nothing exists, or nothing was
    missed) is skipped.
    """
    if not output.get("available"):
        return
    jobs = output.get("jobs") or []
    truncated = output.get("truncated", False)
    if not jobs and not truncated:
        return
    total = output.get("total", len(jobs))
    total_label = f"{total}+" if truncated else str(total)
    failing = _count_with_status(jobs, _FAILED_JOB_STATUSES)
    failing_label = f"{failing}+" if truncated else str(failing)
    record_evidence_entry(
        evidence,
        source="list_jenkins_jobs",
        label="Jenkins Jobs",
        summary=f"{total_label} job(s), {failing_label} failing{_unstable_suffix(jobs, truncated)}",
    )


def map_list_jenkins_running_builds(
    evidence: dict[str, Any], output: dict[str, Any], _tool_input: dict[str, Any]
) -> None:
    """Cite how many builds are currently running.

    ``truncated`` is the client's own explicit signal (folder-depth or job
    cap dropped some jobs from the scan), not an inferred heuristic. A
    depth-limited scan whose only running builds lie beyond the boundary
    returns an empty ``running_builds`` list with ``truncated`` still set --
    that incompleteness is itself worth citing, so only an empty *and*
    untruncated result is skipped.
    """
    if not output.get("available"):
        return
    running = output.get("running_builds") or []
    truncated = output.get("truncated", False)
    if not running and not truncated:
        return
    total = output.get("total", len(running))
    total_label = f"{total}+" if truncated else str(total)
    record_evidence_entry(
        evidence,
        source="list_jenkins_running_builds",
        label="Jenkins Running Builds",
        summary=f"{total_label} build(s) currently running",
    )
