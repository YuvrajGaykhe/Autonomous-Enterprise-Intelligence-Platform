"""
G2 secret hygiene (spec Section 14 and Section 21).

scripts/secret_scan.py finds credential-shaped values in tracked files and
checks .env hygiene without ever printing a matched value; the repository
itself must scan clean. Settings never show credentials in repr, and the
shared engine factory never echoes SQL or bound parameters.

Credential-shaped samples below are assembled at runtime from fragments, so
this file does not itself contain a scannable secret.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import database
from app.core.config import Settings

REPO = Path(__file__).resolve().parents[2]
CANARY = "g2-synthetic-settings-canary"
PASSWORD = "Rt7kLm2" + "pQx9vW4"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("secret_scan_g2", REPO / "scripts" / "secret_scan.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their defining module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scan = _load_scanner()


def _single(path: str, text: str):
    findings = scan.scan_text(path, text)
    assert len(findings) == 1, findings
    return findings[0]


# --- provider-specific rules -----------------------------------------------------------

PROVIDER_SAMPLES = {
    "private_key": ("-----BEGIN " + "RSA PRIVATE KEY-----", "-----BEGIN " + "RSA PRIVATE KEY-----"),
    "aws_access_key_id": ("AK" + "IA" + "ABCDEFGHIJKLMNOP", "AK" + "IA" + "ABCDEFGHIJKLMNOP"),
    "github_token": ("gh" + "p_" + "a1" * 18, "gh" + "p_" + "a1" * 18),
    "slack_token": ("xo" + "xb-" + "1234567890-abcdef", "xo" + "xb-" + "1234567890-abcdef"),
    "sk_api_key": ("sk" + "-ant-" + "b2" * 12, "sk" + "-ant-" + "b2" * 12),
    "google_api_key": ("AI" + "za" + "c" * 35, "AI" + "za" + "c" * 35),
    "jwt": ("ey" + "J" + "a" * 10 + ".ey" + "J" + "b" * 10 + "." + "c" * 10,
            "ey" + "J" + "a" * 10 + ".ey" + "J" + "b" * 10 + "." + "c" * 10),
}


@pytest.mark.parametrize("rule", sorted(PROVIDER_SAMPLES))
def test_provider_rules_find_values_with_line_and_fingerprint(rule):
    text, value = PROVIDER_SAMPLES[rule]
    finding = _single("app/module.py", f"first line\nsecond line\nx = '{text}'\n")
    assert finding == scan.Finding("app/module.py", 3, rule, scan.fingerprint(value))


def test_provider_rules_ignore_placeholder_markers():
    value = "AK" + "IA" + "EXAMPLEEXAMPLEEX"
    assert _single("README.md", value).rule == "aws_access_key_id"


@pytest.mark.parametrize("text", [
    "AK" + "IA" + "ABCDEFGHIJKLMNO", "gh" + "p_" + "a" * 35, "sk" + "-" + "a" * 19,
    "AI" + "za" + "c" * 34, "ey" + "J" + "a" * 10 + "." + "b" * 10 + "." + "c" * 10,
    "-----BEGIN " + "PUBLIC KEY-----", "xo" + "xb-" + "123",
])
def test_near_misses_are_not_findings(text):
    assert scan.scan_text("app/module.py", text) == []


# --- generic rules --------------------------------------------------------------------


def test_url_credentials_fingerprint_the_password_only():
    finding = _single("docs/deploy.md", f"postgresql://svc:{PASSWORD}@db:5432/app")
    assert (finding.rule, finding.fingerprint) == ("url_credentials", scan.fingerprint(PASSWORD))


@pytest.mark.parametrize("password", ["changeme", "${POSTGRES_PASSWORD:-changeme}",
                                      "{self.postgres_password}", "short12", "g2-synthetic-password",
                                      "placeholder", "not-a-secret-at-all", "%(password)s"])
def test_url_credentials_skip_placeholders_templates_and_short_values(password):
    assert scan.scan_text("docker-compose.yml", f"postgresql://svc:{password}@db/app") == []


@pytest.mark.parametrize("marker", ["changeme", "placeholder", "synthetic", "example", "not-a-secret",
                                    "dummy", "fake", "redacted", "xxxx", "{", "}", "<", ">", "$",
                                    "%(", "*"])
def test_each_placeholder_marker_skips_generic_values_case_insensitively(marker):
    value = f"Ab3{marker.upper()}dE6gH9"
    real = "Ab3" + "dE6gH9"
    assert scan.scan_text("docs/x.md", f"postgresql://svc:{value}@db/app") == []
    assert len(scan.scan_text("docs/x.md", f"postgresql://svc:{real}@db/app")) == 1


def test_bearer_tokens_are_found_on_one_line_only():
    sample = "abcDEF1" + "23456gh" + "iJKL"
    assert _single("app/x.py", f"Authorization: Bearer {sample}").fingerprint == scan.fingerprint(sample)
    assert _single("app/x.py", f"bearer\t{sample}").rule == "bearer_token"
    assert scan.scan_text("README.md", "mechanism: bearer\n\nentities:") == []
    # A token-shaped word on the next line is not a bearer credential either.
    assert scan.scan_text("README.md", "mechanism: bearer\nX9kLm2pQx7") == []


@pytest.mark.parametrize("text", ["bearer credentials and more", "Bearer tokens", "Bearer abc123",
                                  "Bearer {token}"])
def test_bearer_prose_short_and_template_values_are_skipped(text):
    assert scan.scan_text("config/validation/quality_gate.yaml", text) == []


def test_mixed_case_bearer_words_are_still_tokens():
    assert _single("app/x.py", "Bearer " + "Credentials").rule == "bearer_token"


@pytest.mark.parametrize("text", [
    f'api_key = "{PASSWORD}"', f"\"client_secret\": '{PASSWORD}'", f'DB_PASSWORD="{PASSWORD}"',
    f'  accessKey: "{PASSWORD}"', f'self.auth_token="{PASSWORD}"',
])
def test_quoted_secret_assignments_are_found_in_any_file(text):
    for path in ("app/x.py", "config/x.yaml", "README.md"):
        finding = _single(path, text)
        assert (finding.rule, finding.fingerprint) == ("quoted_secret_assignment",
                                                       scan.fingerprint(PASSWORD))


@pytest.mark.parametrize("text", [
    'password = "changeme123"', 'token = "${TOKEN}"', 'secret = "short"', "token_count = 12345678",
    'name = "Rt7kLm2pQx9vW4"', 'password =\n"Rt7kLm2pQx9vW4"',
])
def test_other_assignments_are_not_quoted_secret_findings(text):
    assert scan.scan_text("app/x.py", text) == []


@pytest.mark.parametrize("path", [".env", ".env.production", "config/app.ini", "deploy/run.sh",
                                  "settings.cfg", "db.conf", "app.properties", "prod.env",
                                  "config/APP.INI"])
def test_env_style_assignments_are_found_in_env_style_files(path):
    for text in (f"POSTGRES_PASSWORD={PASSWORD}", f"export API_TOKEN={PASSWORD}  # prod",
                 f"  db_secret = {PASSWORD}"):
        finding = _single(path, text)
        assert (finding.rule, finding.fingerprint) == ("env_secret_assignment",
                                                       scan.fingerprint(PASSWORD))


@pytest.mark.parametrize("path", ["app/x.py", "README.md", "Makefile", "config/x.yaml"])
def test_env_style_assignments_are_ignored_elsewhere(path):
    assert scan.scan_text(path, f"null_tokens = default_tokens_{PASSWORD}") == []
    assert scan.scan_text(path, f"POSTGRES_PASSWORD={PASSWORD}") == []


def test_env_style_placeholders_and_line_breaks_are_skipped():
    assert scan.scan_text(".env.example", "POSTGRES_PASSWORD=changeme\nAPI_KEY=${API_KEY}\n") == []
    assert scan.scan_text(".env", "POSTGRES_PASSWORD=\nAPP_PORT=8000123\n") == []


@pytest.mark.parametrize("path", ["config/connectors/rest.yaml", "compose.yml", "X.YAML"])
def test_unquoted_yaml_secrets_are_found_in_yaml_only(path):
    finding = _single(path, f"auth:\n  api_key: {PASSWORD}\n")
    assert (finding.line, finding.rule, finding.fingerprint) == (
        2, "yaml_secret_assignment", scan.fingerprint(PASSWORD))
    assert scan.scan_text("notes.md", f"auth:\n  api_key: {PASSWORD}\n") == []


@pytest.mark.parametrize("text", ["password: ${DB_PASSWORD}", "token: changeme-token",
                                  "sensitive_keys:\n  - password", "password: short",
                                  "password: rotate-monthly via vault", "env_var: REST_API_TOKEN"])
def test_yaml_placeholders_lists_and_non_secret_keys_are_skipped(text):
    assert scan.scan_text("config/x.yaml", text) == []


def test_allowed_findings_are_pinned_to_path_rule_and_fingerprint(monkeypatch):
    text = f'api_key = "{PASSWORD}"'
    digest = scan.fingerprint(PASSWORD)
    monkeypatch.setattr(scan, "ALLOWED_FINDINGS",
                        {("tests/a.py", "quoted_secret_assignment", digest): "synthetic"})
    assert scan.scan_text("tests/a.py", text) == []
    assert len(scan.scan_text("tests/b.py", text)) == 1
    monkeypatch.setattr(scan, "ALLOWED_FINDINGS",
                        {("tests/a.py", "bearer_token", digest): "synthetic"})
    assert len(scan.scan_text("tests/a.py", text)) == 1


def test_every_allowed_finding_has_a_reason_and_is_still_needed():
    for (path, rule, digest), reason in scan.ALLOWED_FINDINGS.items():
        assert reason and len(digest) == scan.FINGERPRINT_LENGTH
        text = (REPO / path).read_text(encoding="utf-8")
        original = dict(scan.ALLOWED_FINDINGS)
        try:
            scan.ALLOWED_FINDINGS.clear()
            assert any(f.rule == rule and f.fingerprint == digest for f in scan.scan_text(path, text))
        finally:
            scan.ALLOWED_FINDINGS.update(original)


def test_fingerprints_are_short_sha256_prefixes_and_findings_never_show_values():
    assert scan.FINGERPRINT_LENGTH == 12
    assert scan.fingerprint("abc") == "ba7816bf8f01"
    finding = _single("app/x.py", f'api_key = "{PASSWORD}"')
    assert str(finding) == f"app/x.py:1: quoted_secret_assignment [{scan.fingerprint(PASSWORD)}]"
    assert PASSWORD not in str(finding) and PASSWORD not in repr(finding)


def test_generic_minimum_length_is_eight():
    assert scan.GENERIC_MIN_LENGTH == 8
    assert scan.scan_text("app/x.py", 'token = "Ab3dE6g"') == []
    assert len(scan.scan_text("app/x.py", 'token = "' + "Ab3dE6gH" + '"')) == 1


# --- hygiene --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [".env", "config/.env", ".env.local", ".env.production", "prod.env"])
def test_tracked_env_files_are_findings(path):
    findings = scan.check_hygiene([path, ".env.example"], ".env\n", "")
    assert findings == [scan.Finding(path, 0, "tracked_env_file", scan.fingerprint(path))]


def test_gitignore_must_ignore_env():
    for gitignore in (None, "", ".env.local\n", "# .env\n", "env\n"):
        assert scan.check_hygiene([], gitignore, "") == [
            scan.Finding(".gitignore", 0, "env_not_ignored", scan.fingerprint(".env"))]
    assert scan.check_hygiene([], "*.pyc\n  .env  \n", "") == []


def test_env_example_secrets_must_be_placeholders():
    example = ("APP_PORT=8000\nPOSTGRES_PASSWORD=changeme\nODOO_API_KEY=\n"
               f"REST_API_TOKEN={PASSWORD}\nINTERNAL_SECRET_KEY=changeme-replace-me\n"
               "WEBHOOK_SECRET=CHANGEME\nCLIENT_TOKEN=Replace-With-EXAMPLE-Value\n")
    assert scan.check_hygiene([], ".env\n", example) == [
        scan.Finding(".env.example", 4, "env_example_value", scan.fingerprint(PASSWORD))]


def test_the_committed_hygiene_files_pass():
    tracked = scan.tracked_files(REPO)
    assert ".env" not in tracked and ".env.example" in tracked
    assert scan.check_hygiene(tracked, (REPO / ".gitignore").read_text(encoding="utf-8"),
                              (REPO / ".env.example").read_text(encoding="utf-8")) == []


# --- repository scan and command ------------------------------------------------------


def _git_repo(tmp_path: Path, files: dict[str, bytes]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def test_repository_scans_cover_tracked_text_files_and_skip_binaries(tmp_path):
    repo = _git_repo(tmp_path, {
        ".gitignore": b".env\n", "app/settings.py": f'api_key = "{PASSWORD}"\n'.encode(),
        "docs/image.gif": b"GIF89a\x00\x00" + f'api_key = "{PASSWORD}"'.encode(),
        "docs/latin.txt": b"\xff\xfe" + f'api_key = "{PASSWORD}"'.encode("utf-16-le"),
        "docs/clean.md": b"nothing here\n",
        "app/deleted.py": f'api_key = "{PASSWORD}"\n'.encode(),
    })
    (repo / "untracked.py").write_text(f'api_key = "{PASSWORD}"\n', encoding="utf-8")
    (repo / "app" / "deleted.py").unlink()  # tracked but removed from the working tree
    report = scan.scan_repository(repo)
    assert (report.scanned, report.skipped_binary) == (3, 2)
    assert report.findings == (scan.Finding("app/settings.py", 1, "quoted_secret_assignment",
                                            scan.fingerprint(PASSWORD)),)


def test_the_command_prints_findings_without_values(tmp_path, capsys):
    repo = _git_repo(tmp_path, {".gitignore": b"", "app/settings.py": f'api_key = "{PASSWORD}"\n'.encode()})
    assert scan.main([], repo) == 1
    output = capsys.readouterr()
    assert output.out.splitlines() == [
        f".gitignore:0: env_not_ignored [{scan.fingerprint('.env')}]",
        f"app/settings.py:1: quoted_secret_assignment [{scan.fingerprint(PASSWORD)}]",
        "secret-scan: 2 files scanned, 0 binary files skipped, 2 findings",
    ]
    assert PASSWORD not in output.out + output.err


def test_the_command_reports_errors_and_rejects_arguments(tmp_path, capsys):
    assert scan.main([], tmp_path) == 2
    assert capsys.readouterr().err == "secret-scan: not a git checkout\n"
    assert scan.main(["--fix"], REPO) == 2
    assert capsys.readouterr().err == "usage: python scripts/secret_scan.py\n"


def test_tracked_files_requires_git(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(scan.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match=r"^git is unavailable \(FileNotFoundError\)$"):
        scan.tracked_files(REPO)


def test_the_repository_has_no_committed_secrets(capsys):
    report = scan.scan_repository(REPO)
    assert report.findings == ()
    assert report.scanned > 150 and report.skipped_binary >= 3
    assert scan.main([], REPO) == 0
    assert capsys.readouterr().out.endswith(" 0 findings\n")


# --- settings and engine --------------------------------------------------------------


def test_settings_never_show_credentials():
    settings = Settings(postgres_password=CANARY, database_url=f"postgresql://svc:{CANARY}@db/app")
    for text in (repr(settings), str(settings)):
        assert CANARY not in text
        assert "postgres_user='ai_ceo'" in text
    assert settings.postgres_password == CANARY
    assert settings.effective_database_url == f"postgresql://svc:{CANARY}@db/app"
    assert settings.model_dump()["postgres_password"] == CANARY


def test_constructed_database_urls_still_use_the_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None, postgres_password=CANARY, database_url=None)
    assert settings.effective_database_url == f"postgresql://ai_ceo:{CANARY}@localhost:5432/ai_ceo_layer1"
    assert CANARY not in repr(settings)


def test_the_engine_factory_never_echoes_sql_or_parameters(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", f"postgresql://svc:{CANARY}@127.0.0.1:9/app")
    engine = database.get_engine()
    try:
        assert engine.echo is False
        assert engine.hide_parameters is True
        assert CANARY not in repr(engine)
    finally:
        engine.dispose()
