#!/usr/bin/env python3
"""Validate one OCI security-token profile without exposing debug output."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence, Union


PROFILE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
REGION_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+-\d+$")
IDENTITY_REGION_RE = re.compile(
    r"https://identity\.([a-z0-9-]+)\.oci\.oraclecloud\.com"
)
TENANCY_ID_RE = re.compile(r"/tenancies/(ocid1\.tenancy\.[^/?\s]+)")
VALID_UNTIL_RE = re.compile(r"Session is valid until\s+(.+)", re.IGNORECASE)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# OCI CLI's message for an expired session; any other failure that merely
# mentions "expired" (for example a TLS certificate) is reported as invalid.
EXPIRED_MARKER = "session has expired"
DETAIL_MAX_LENGTH = 300

SESSION_TIMEOUT_SECONDS = 15
DISCOVERY_TIMEOUT_SECONDS = 20
TENANCY_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class CommandResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    launch_error: bool = False


def _as_text(value: Union[str, bytes, None]) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _run(args: Sequence[str], timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            check=False,
            # `oci session validate` asks interactively to re-authenticate an
            # expired session; closed input makes it abort instead of waiting.
            stdin=subprocess.DEVNULL,
            shell=False,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            returncode=None,
            stdout=_as_text(exc.stdout),
            stderr=_as_text(exc.stderr),
            timed_out=True,
        )
    except OSError:
        return CommandResult(
            returncode=None,
            stdout="",
            stderr="",
            launch_error=True,
        )


def _unique_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    return list(dict.fromkeys(pattern.findall(text)))


def _emit(status: str, profile: str, target_region: str, **fields: str) -> int:
    payload = {
        "profile": profile,
        "status": status,
        "targetRegion": target_region,
    }
    payload.update({key: value for key, value in fields.items() if value})
    print(json.dumps(payload, sort_keys=True))
    return 0


def _failure_detail(text: str) -> str:
    """Return OCI's error line, bounded for display.

    The ERROR line is preferred over leftovers such as an aborted prompt.
    """
    lines = [line.strip() for line in ANSI_RE.sub("", text).splitlines() if line.strip()]
    chosen = next((line for line in lines if line.upper().startswith("ERROR")), lines[0] if lines else "")
    return chosen[:DETAIL_MAX_LENGTH]


def _classify_validation_failure(text: str) -> str:
    lowered = text.lower()
    if EXPIRED_MARKER in lowered:
        return "expired"
    if "profile" in lowered and any(
        marker in lowered
        for marker in ("not found", "does not exist", "could not find", "missing")
    ):
        return "profile_missing"
    return "invalid"


def validate(profile: str, target_region: str, oci_path: str = "oci") -> int:
    if not PROFILE_RE.fullmatch(profile):
        return _emit("invalid_input", profile, target_region, reason="invalid_profile")
    if not REGION_RE.fullmatch(target_region):
        return _emit("invalid_input", profile, target_region, reason="invalid_region")
    if shutil.which(oci_path) is None:
        return _emit("oci_unavailable", profile, target_region)

    session = _run(
        [
            oci_path,
            "session",
            "validate",
            "--profile",
            profile,
            "--auth",
            "security_token",
        ],
        SESSION_TIMEOUT_SECONDS,
    )
    if session.timed_out:
        return _emit(
            "validation_unavailable",
            profile,
            target_region,
            reason="session_validation_timeout",
        )
    if session.launch_error:
        return _emit(
            "validation_unavailable",
            profile,
            target_region,
            reason="oci_launch_failed",
        )
    if session.returncode != 0:
        output = session.stderr + "\n" + session.stdout
        failure = _classify_validation_failure(output)
        return _emit(failure, profile, target_region, detail=_failure_detail(output))

    result_fields: dict[str, str] = {}
    valid_until_match = VALID_UNTIL_RE.search(session.stdout + session.stderr)
    if valid_until_match:
        result_fields["validUntil"] = valid_until_match.group(1).strip()

    discovery = _run(
        [
            oci_path,
            "iam",
            "region-subscription",
            "list",
            "--profile",
            profile,
            "--auth",
            "security_token",
            "--debug",
        ],
        DISCOVERY_TIMEOUT_SECONDS,
    )
    debug_text = discovery.stdout + discovery.stderr
    regions = _unique_matches(IDENTITY_REGION_RE, debug_text)
    tenancy_ids = _unique_matches(TENANCY_ID_RE, debug_text)

    if len(regions) == 1:
        result_fields["profileRegion"] = regions[0]
        if regions[0] != target_region:
            return _emit(
                "region_mismatch", profile, target_region, **result_fields
            )

    if discovery.timed_out:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="region_discovery_timeout",
            **result_fields,
        )
    if discovery.launch_error:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="oci_launch_failed",
            **result_fields,
        )
    if discovery.returncode != 0:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="region_discovery_failed",
            **result_fields,
        )
    if len(regions) != 1:
        reason = "region_not_found" if not regions else "multiple_regions"
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason=reason,
            **result_fields,
        )
    if len(tenancy_ids) != 1:
        reason = "tenancy_not_found" if not tenancy_ids else "multiple_tenancies"
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason=reason,
            **result_fields,
        )

    tenancy = _run(
        [
            oci_path,
            "iam",
            "tenancy",
            "get",
            "--profile",
            profile,
            "--auth",
            "security_token",
            "--tenancy-id",
            tenancy_ids[0],
            "--query",
            "data.name",
            "--raw-output",
        ],
        TENANCY_TIMEOUT_SECONDS,
    )
    if tenancy.timed_out:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="tenancy_lookup_timeout",
            **result_fields,
        )
    if tenancy.launch_error:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="oci_launch_failed",
            **result_fields,
        )
    if tenancy.returncode != 0:
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="tenancy_lookup_failed",
            **result_fields,
        )

    tenancy_name = tenancy.stdout.strip()
    if not tenancy_name or tenancy_name.lower() == "null":
        return _emit(
            "active_details_unavailable",
            profile,
            target_region,
            reason="tenancy_name_empty",
            **result_fields,
        )

    result_fields["tenancyName"] = tenancy_name
    return _emit("active", profile, target_region, **result_fields)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one OCI security-token profile for AIDP setup."
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--target-region", required=True)
    args = parser.parse_args()
    return validate(args.profile, args.target_region)


if __name__ == "__main__":
    raise SystemExit(main())
