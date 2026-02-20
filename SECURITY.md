# Security Policy

## Scope and Maintainer Availability

`tz-player` is maintained by a single developer.

Security triage and remediation are handled on a best-effort basis. Due to disability-related capacity constraints and other obligations, response and fix timelines may vary widely and can be delayed for extended periods (including months).

If you need guaranteed response timelines, this project may not meet that requirement.

## Reporting a Vulnerability

Please open a private GitHub security advisory or email the maintainer at 15974146+taggedzi@users.noreply.github.com.
Include:

- a clear description of the issue
- steps to reproduce
- affected versions/commit
- impact assessment and potential exploitability

Please avoid public disclosure until the issue has been assessed.

## Response Expectations

- Receipt acknowledgements are best-effort and not guaranteed within a fixed timeframe.
- Triage priority is based on impact, exploitability, and maintainer capacity.
- Fixes may be released quickly for critical issues, or delayed when capacity is constrained.

## Third-Party Visualizer Plugins

Visualizer plugins are Python code and execute with the same user permissions as the app process.

- Only install plugins from sources you trust.
- The app includes static plugin safety checks (`off`, `warn`, `enforce`) to detect common risky patterns.
- The app can run local plugins in a process-isolated mode (`--visualizer-plugin-runtime isolated`) with timeout-based failover.
- These checks reduce risk but do not provide complete sandboxing of arbitrary Python code.
- For higher assurance, run only reviewed plugins in constrained OS environments.

## Dependency Strategy

- Keep direct dependencies minimal and review new additions.
- Prefer version ranges with upper bounds for production deployments.
- Use `pip install --require-hashes` or a lockfile (for example `pip-tools`) for releases.

## Secrets and Sensitive Data

- Do not commit secrets or credentials to the repository.
- Use environment variables or OS keychains for secrets.
- Scrub logs and error messages that may include sensitive data.

## Safe File Handling

- Validate and normalize file paths before access.
- Avoid writing outside intended directories.
- Use atomic writes for critical files and handle permissions explicitly.
