# Exact candidate OS advisory review — October 4, 2026

The final completed amd64 scan of image
`sha256:14e4081f4f84af51b321f6fff75c2451401bc70b0f56ce57d147d7d261b53713`
reported **0 CRITICAL, 44 HIGH, 61 MEDIUM, 60 LOW, 2 UNKNOWN**, with zero Python
package findings. It belongs to frozen source
`73eb35d6be24bed880bef74ed1c237b2d649d6985ed8bb2d1753a965c7830af6`.
Full scanner output is preserved privately; the redacted exact-match assessment is
[retained](production-completion-complete-image-assessment-2026-10-04.json).
Earlier image assessments are separate dated evidence. No finding was hidden and
no risk exception was approved. The final normal-entrypoint inspection reconfirmed
mount/nsenter/infocmp present, systemd-homed absent and Archive::Tar unavailable.

The HIGH count contains repeated binary-package matches from eight distinct CVEs,
not 44 independently demonstrated application exploits. Debian's current tracker
lists these installed trixie source-package versions as vulnerable; none of the
remaining HIGH matches had an available fixed trixie version in the scanner.
Mixing unstable distribution packages into this pinned production image was not
performed. The available PCRE2 patch was applied and removed that prior HIGH match.

| Finding | Installed functionality and reachable-path assessment | Remaining decision |
| --- | --- | --- |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) | util-linux 2.41.5: privileged mount helper/post-hook behavior. mount/nsenter are installed. Application workers do not call them in reviewed launch paths. | Actual host privileges, fstab/mount policy and operator behavior are UNVERIFIED; review exact binary matches. |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) | nsenter privileged join-cgroup descriptor inheritance. nsenter is installed; no reviewed application invocation. | Host/operator namespace usage and privilege boundaries require review. |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409), [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | fstab-authorized mount subdirectory/bind behavior. mount is installed; no reviewed application invocation. | Actual kernel, fstab, writable ancestors, capabilities and mount privileges are UNVERIFIED. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | ncurses 6.5: infocmp parser overflow; infocmp is installed. No reviewed web/provider path invokes infocmp. The retained nano editor uses ncurses libraries. | Do not infer every library match exposes the CLI parser, or remove a working editor solely to suppress the scan. Review exact installed components. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | libsystemd0/libudev1 257.13 are present; `systemd-homed` is absent in the tested image. | This materially limits the described homed attack path, but an exact package/version/architecture disposition is still required. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | libacl1 2.3.2 pathname/symlink race. Library is installed; malicious filename/path controls remain protected by application checks. | Library presence and application path validation are not complete proof of non-exploitability; host ACL consumers remain UNVERIFIED. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | perl-base 5.40.1 is present. `perl -MArchive::Tar` fails because the described module is absent. Reviewed application code does not use Perl tar extraction. | Verify the final image remains without the module, then obtain a named exact-match disposition if accepting the scanner's source-package match. |

These are scoped observations and inferences, not blanket “not affected” claims.
The image's normal entrypoint drops to UID 1000, while the read-only package
inventory deliberately used an overridden inspection entrypoint. Target runtime
capabilities, mounts and service hardening were not inspected. No exploit or
questionable credential was executed.

A risk owner must either supply a tested compatible patch/base update or enter a
reviewer, rationale, primary evidence, exact package/version/architecture and expiry
in `docs/production-image-risk-decisions.json`. That file intentionally contains
no approvals. The automated image gate remains FAIL until every HIGH/CRITICAL
match is resolved by this process. Retain the complete MEDIUM/LOW/UNKNOWN output
for continuing review.
