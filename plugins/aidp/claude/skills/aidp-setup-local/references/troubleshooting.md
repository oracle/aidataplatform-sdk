# Local setup troubleshooting

Use this reference when normal setup encounters a package lookup or installation problem, or when `/oracle-aidp:doctor` finds one. Reuse the selected interpreter, environment, captured error and existing session state; do not rerun successful checks or require a separate doctor invocation to recover during setup.

Doctor remains read-only: diagnose and offer the smallest corrective step. Run installations, repairs, or process termination only through the authorized setup flow. Authentication and AIDP access errors keep their existing procedures in [profile validation](oci-profile-validation.md) and [target selection](aidp-target-selection.md#handle-the-first-access-failure).

## Package download timeouts

For a package-index lookup or pip installation timeout, first apply the skill’s host network-permission handling. If it still times out with network access, ask once:

> <Operation> is timing out. Would you like to disconnect from VPN and retry, or use your company’s Python package server if IT has provided one?

Replace `<Operation>` with the actual action, such as `Checking the latest AIDP CLI version`, `Installing OCI CLI`, or `Installing AIDP CLI`. This offers an option; do not claim VPN caused the timeout or disconnect it yourself. Wait for the user’s choice. If they choose VPN disconnection, wait for confirmation before retrying the failed operation once. If they choose a company server, use only their supplied package-index settings; do not guess a URL or request credentials in chat. Preserve existing proxy and certificate settings. A further timeout is reported without another automatic retry.

Only after all planned installations, upgrades, and download recovery finish and final prerequisite checks pass, follow the skill’s VPN reminder rule; do not give the reminder during download recovery. Package-index lookup success alone is not installation completion.

## Stalled or interrupted installation

Pip’s socket timeout bounds a stalled network read, not the total installation. Preserve existing timeout settings rather than automatically increasing them and rerunning pip. Keep polling the original installer session while it progresses; quiet output alone is not evidence of a hang. Avoid repeated CPU/process listings, directory counts, or a second installer to check progress.

After a prolonged unexplained lack of progress, inspect the original session and perform a targeted diagnostic. If it is genuinely stuck, state the evidence briefly, stop that exact process, wait for it to exit, check installed state, and retry only what is missing, once. Never start a replacement while the original installer is still running.

On a nonzero exit, inspect the captured error and apply the relevant recovery guidance. If the session is lost or completion is uncertain, report that uncertainty and check the installed state before retrying; do not claim success or blindly reinstall. A reported download timeout follows the package timeout procedure above.

## Windows path and script errors

Retain the exact error and failing path; do not infer that every file error is
a path-length error. For Windows OCI preparation or installation failures, use
the [MSI recovery procedure](installation.md#windows-oci-msi-fallback) instead of
generic pip retry guidance. For AIDP folder-access failures, use
[Windows directory preparation](windows.md#installation-directory-selection).
ACL changes do not solve path-length or network/dependency errors.

After an authorized repair, return to [final installation verification](installation.md#final-verification). Keep dependencies enabled and preserve package-index, proxy and certificate settings.
