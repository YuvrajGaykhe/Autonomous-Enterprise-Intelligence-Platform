"""
Repository secret hygiene scan (spec Section 14 "Never commit real secrets,
tokens, cookies, or exported enterprise data"; Section 21 "Secrets in .env
committed to Git").

    python scripts/secret_scan.py          (make secret-scan)

Scans every file tracked by git. Exit status:
    0  no findings
    1  findings (each printed as "path:line: rule [fingerprint]")
    2  the scan could not run (not a git checkout, git unavailable, arguments)

Content rules find credential-shaped values: private keys, cloud and SaaS
tokens, JWTs, credentials embedded in URLs, bearer tokens, quoted assignments
to password/secret/token/key names, and unquoted assignments to such names in
environment-style files (.env, .ini, .cfg, .conf, .properties, .sh) and YAML.
Hygiene rules require that no .env file is tracked (only .env.example), that
.gitignore ignores .env, and that every secret-like variable in .env.example
has a placeholder value.

Findings never print the matched value: only its path, line, rule and a
12-character SHA-256 fingerprint, so the scan output is itself safe to share.

Generic rules (URL credentials, bearer tokens, assignments) skip values that
visibly mark themselves as placeholders or templates (PLACEHOLDER_MARKERS) or
are shorter than GENERIC_MIN_LENGTH; the bearer rule also skips plain
lowercase words, which are prose ("bearer credentials"), not tokens.
Provider-specific rules (keys, tokens, JWTs) skip nothing. Any other accepted
value is pinned in ALLOWED_FINDINGS by path, rule and fingerprint, with the
reason it is safe.

Binary files (PDF, PPTX, images) are skipped and counted, not scanned.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent
FINGERPRINT_LENGTH = 12
GENERIC_MIN_LENGTH = 8
BINARY_PROBE_BYTES = 8192
PLACEHOLDER_MARKERS = ("changeme", "placeholder", "synthetic", "example", "not-a-secret", "dummy",
                       "fake", "redacted", "xxxx", "{", "}", "<", ">", "$", "%(", "*")
SECRET_NAME = r"(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
ENV_STYLE_SUFFIXES = frozenset({".env", ".ini", ".cfg", ".conf", ".properties", ".sh"})
YAML_SUFFIXES = frozenset({".yml", ".yaml"})
ENV_EXAMPLE = ".env.example"
PROSE_WORD = re.compile(r"[a-z]+")


def any_file(path: str) -> bool:
    return True


def env_style_file(path: str) -> bool:
    name = PurePosixPath(path)
    return name.name.startswith(".env") or name.suffix.lower() in ENV_STYLE_SUFFIXES


def yaml_file(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in YAML_SUFFIXES


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    generic: bool
    group: int = 0
    applies_to: Callable[[str], bool] = any_file
    skip_prose: bool = False


RULES = (
    Rule("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), generic=False),
    Rule("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), generic=False),
    Rule("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
         generic=False),
    Rule("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), generic=False),
    Rule("sk_api_key", re.compile(r"\bsk-(?:ant-|proj-|live_|test_)?[A-Za-z0-9_-]{20,}"), generic=False),
    Rule("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), generic=False),
    Rule("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
         generic=False),
    Rule("url_credentials",
         re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@'\"]+:([^\s/@'\"]+)@"), generic=True, group=1),
    Rule("bearer_token", re.compile(r"(?i)\bbearer[ \t]+([A-Za-z0-9._~+/-]+=*)"), generic=True, group=1,
         skip_prose=True),
    Rule("quoted_secret_assignment",
         re.compile(rf"(?i)\b[A-Za-z0-9_.-]*{SECRET_NAME}[A-Za-z0-9_.-]*[\"']?[ \t]*[:=][ \t]*"
                    r"[\"']([^\"'\s]+)[\"']"),
         generic=True, group=1),
    Rule("env_secret_assignment",
         re.compile(rf"(?im)^[ \t]*(?:export[ \t]+)?[A-Z0-9_]*{SECRET_NAME}[A-Z0-9_]*[ \t]*=[ \t]*"
                    r"([^\s#\"']+)"),
         generic=True, group=1, applies_to=env_style_file),
    Rule("yaml_secret_assignment",
         re.compile(rf"(?im)^[ \t]*[A-Za-z0-9_.-]*{SECRET_NAME}[A-Za-z0-9_.-]*[ \t]*:[ \t]*"
                    r"([^\s#\"'][^\s#]*)[ \t]*$"),
         generic=True, group=1, applies_to=yaml_file),
)

# (path, rule, fingerprint) -> why the value is safe. Only clearly synthetic
# test fixtures belong here; never add a real credential.
ALLOWED_FINDINGS: dict[tuple[str, str, str], str] = {
    ("tests/unit/d2_support.py", "quoted_secret_assignment", "f03189b94453"):
        "synthetic D2 redaction fixture TEST_CREDENTIAL_VALUE_FOR_REDACTION",
    ("tests/unit/test_d2_rules.py", "bearer_token", "f03189b94453"):
        "synthetic D2 redaction fixture TEST_CREDENTIAL_VALUE_FOR_REDACTION",
    ("tests/unit/test_d2_quarantine.py", "quoted_secret_assignment", "3d61763ea0e2"):
        "synthetic D2 quarantine leak-test value",
    ("tests/unit/test_d2_quarantine.py", "quoted_secret_assignment", "e25f5c0de43a"):
        "synthetic D2 quarantine leak-test value",
    ("tests/unit/test_c5_rest_connector.py", "quoted_secret_assignment", "625faa3fbbc3"):
        "synthetic C5 API-key header test value",
    ("tests/unit/test_c5_rest_connector.py", "bearer_token", "fece50d2287f"):
        "synthetic C5 bearer header test value",
}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    fingerprint: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} [{self.fingerprint}]"


@dataclass(frozen=True)
class Report:
    scanned: int
    skipped_binary: int
    findings: tuple[Finding, ...]


def fingerprint(value: str) -> str:
    """A short, non-reversible identifier for a matched value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def is_placeholder(value: str) -> bool:
    """True if a generic-rule value is visibly not a real credential."""
    lowered = value.lower()
    return len(value) < GENERIC_MIN_LENGTH or any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def scan_text(path: str, text: str) -> list[Finding]:
    """Content findings for one file's text."""
    findings = []
    for rule in RULES:
        if not rule.applies_to(path):
            continue
        for match in rule.pattern.finditer(text):
            value = match.group(rule.group)
            if rule.generic and is_placeholder(value):
                continue
            if rule.skip_prose and PROSE_WORD.fullmatch(value):
                continue
            digest = fingerprint(value)
            if (path, rule.name, digest) in ALLOWED_FINDINGS:
                continue
            findings.append(Finding(path, text.count("\n", 0, match.start()) + 1, rule.name, digest))
    return findings


def check_hygiene(tracked: Iterable[str], gitignore: str | None, env_example: str | None) -> list[Finding]:
    """Findings for tracked .env files, an unignored .env and non-placeholder .env.example values."""
    findings = []
    for path in tracked:
        name = PurePosixPath(path).name
        if (name.startswith(".env.") or name.endswith(".env")) and name != ENV_EXAMPLE:
            findings.append(Finding(path, 0, "tracked_env_file", fingerprint(path)))
    ignored = {line.strip() for line in (gitignore or "").splitlines()}
    if ".env" not in ignored:
        findings.append(Finding(".gitignore", 0, "env_not_ignored", fingerprint(".env")))
    assignment = re.compile(rf"^[ \t]*([A-Z0-9_]*{SECRET_NAME}[A-Z0-9_]*)[ \t]*=[ \t]*(.*?)[ \t]*$",
                            re.IGNORECASE)
    for number, line in enumerate((env_example or "").splitlines(), 1):
        match = assignment.match(line)
        if match and match.group(2) and not any(
                marker in match.group(2).lower() for marker in PLACEHOLDER_MARKERS):
            findings.append(Finding(ENV_EXAMPLE, number, "env_example_value", fingerprint(match.group(2))))
    return findings


def tracked_files(repo: Path) -> list[str]:
    """Paths tracked by git, relative to repo.

    Raises:
        RuntimeError: git is unavailable or repo is not a git checkout.
    """
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"git is unavailable ({type(exc).__name__})") from None
    if result.returncode != 0:
        raise RuntimeError("not a git checkout")
    return sorted(path for path in result.stdout.decode("utf-8").split("\0") if path)


def _read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data[:BINARY_PROBE_BYTES]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _optional_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def scan_repository(repo: Path = REPO) -> Report:
    """Scan every tracked file in repo and apply the hygiene rules."""
    tracked = tracked_files(repo)
    findings: list[Finding] = []
    scanned = skipped = 0
    for relative in tracked:
        path = repo / relative
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            skipped += 1
            continue
        scanned += 1
        findings.extend(scan_text(relative, text))
    findings.extend(check_hygiene(tracked, _optional_text(repo / ".gitignore"),
                                  _optional_text(repo / ENV_EXAMPLE)))
    return Report(scanned, skipped, tuple(sorted(findings)))


def main(argv: Sequence[str] | None = None, repo: Path = REPO) -> int:
    if argv:
        print("usage: python scripts/secret_scan.py", file=sys.stderr)
        return 2
    try:
        report = scan_repository(repo)
    except RuntimeError as exc:
        print(f"secret-scan: {exc}", file=sys.stderr)
        return 2
    for finding in report.findings:
        print(finding)
    print(f"secret-scan: {report.scanned} files scanned, {report.skipped_binary} binary files skipped, "
          f"{len(report.findings)} findings")
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
