#!/usr/bin/env python3
"""Local, read-only production deployment preflight.

This script inspects repository state and optionally validates an operator-supplied
production environment file. It never connects to application databases or
external services.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
EXPECTED_MIGRATION_HEAD = "20260811_0039"


class Reporter:
    def __init__(self) -> None:
        self.passes = 0
        self.warnings = 0
        self.failures = 0

    def passed(self, message: str) -> None:
        self.passes += 1
        print(f"PASS: {message}")

    def warning(self, message: str) -> None:
        self.warnings += 1
        print(f"WARNING: {message}")

    def failed(self, message: str) -> None:
        self.failures += 1
        print(f"FAIL: {message}")

    def check(self, condition: bool, success: str, failure: str) -> None:
        if condition:
            self.passed(success)
        else:
            self.failed(failure)


def _migration_heads() -> list[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in (BACKEND / "alembic/versions").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision_match = re.search(
            r'^revision(?:\s*:[^=]+)?\s*=\s*["\']([^"\']+)["\']',
            source,
            re.MULTILINE,
        )
        if not revision_match:
            continue
        revisions.add(revision_match.group(1))
        parent_match = re.search(
            r'^down_revision(?:\s*:[^=]+)?\s*=\s*["\']([^"\']+)["\']',
            source,
            re.MULTILINE,
        )
        if parent_match:
            parents.add(parent_match.group(1))
    return sorted(revisions - parents)


def _check_migrations(reporter: Reporter) -> None:
    heads = _migration_heads()
    reporter.check(
        len(heads) == 1,
        f"exactly one Alembic head exists ({heads[0] if heads else 'none'})",
        f"expected one Alembic head, found {heads}",
    )
    reporter.check(
        heads == [EXPECTED_MIGRATION_HEAD],
        f"Alembic head matches expected release head {EXPECTED_MIGRATION_HEAD}",
        f"Alembic head {heads} does not match expected {EXPECTED_MIGRATION_HEAD}; review this script for the release",
    )


def _check_backend_static(reporter: Reporter) -> None:
    env_example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    config_source = (BACKEND / "app/core/config.py").read_text(encoding="utf-8")
    payment_source = (BACKEND / "app/services/payments/mmg.py").read_text(encoding="utf-8")

    reporter.check(
        "ENABLE_DEV_TEST_CHECKOUT=false" in env_example,
        "backend example disables development checkout",
        "backend/.env.example must disable development checkout",
    )
    reporter.check(
        "CORS_ALLOWED_ORIGINS=https://admitly.onrender.com,https://www.admitlyevents.com,https://admitlyevents.com" in env_example,
        "production CORS example contains only intended Admitly HTTPS origins",
        "backend CORS example is missing the intended production origin set",
    )
    reporter.check(
        "REDIS_URL is required for shared rate limiting" in config_source,
        "production startup requires shared Redis",
        "production shared-Redis startup guard is missing",
    )
    reporter.check(
        "MMG_PROVIDER_MODE must be live when MMG is enabled" in config_source,
        "production startup rejects enabled mock MMG",
        "production mock-MMG startup guard is missing",
    )
    live_failures = (
        "MMG live checkout is not implemented yet.",
        "MMG live refunds are not implemented yet.",
        "MMG live refund lookup is not implemented yet.",
    )
    reporter.check(
        all(marker in payment_source for marker in live_failures),
        "unimplemented live MMG operations fail explicitly instead of returning success",
        "one or more unimplemented live MMG operations no longer fail explicitly",
    )
    reporter.check(
        "_require_mock_allowed()" in payment_source and "Mock MMG behavior is disabled in production." in payment_source,
        "MMG mock provider has a service-level production guard",
        "MMG mock provider production guard is missing",
    )


def _check_clients(reporter: Reporter) -> None:
    mobile_app = json.loads((ROOT / "mobile/app.json").read_text(encoding="utf-8"))
    mobile_package = json.loads((ROOT / "mobile/package.json").read_text(encoding="utf-8"))
    eas_config = json.loads((ROOT / "mobile/eas.json").read_text(encoding="utf-8"))
    expo = mobile_app.get("expo", {})
    extras = expo.get("extra", {})
    plugins = [plugin[0] if isinstance(plugin, list) else plugin for plugin in expo.get("plugins", [])]
    api_url = str(extras.get("apiBaseUrl", ""))

    reporter.check(
        api_url.startswith("https://") and "localhost" not in api_url,
        "mobile production API base URL is HTTPS and non-local",
        "mobile production API base URL is missing, local, or non-HTTPS",
    )
    reporter.check(
        "expo-secure-store" in mobile_package.get("dependencies", {}) and "expo-secure-store" in plugins,
        "mobile includes the SecureStore dependency and native plugin",
        "mobile SecureStore dependency or native plugin is missing",
    )
    reporter.check(
        "@sentry/react-native" in mobile_package.get("dependencies", {}) and "@sentry/react-native" in plugins,
        "mobile includes Sentry dependency and native plugin",
        "mobile Sentry dependency or native plugin is missing",
    )
    reporter.check(
        "production" in eas_config.get("build", {}),
        "mobile EAS production build profile exists",
        "mobile EAS production build profile is missing",
    )
    if eas_config.get("build", {}).get("production", {}).get("channel"):
        reporter.passed("mobile production update channel is explicit")
    else:
        reporter.warning("mobile production update channel is not configured; acceptable only while OTA updates remain intentionally unused")

    admin_example = (ROOT / "admin/.env.example").read_text(encoding="utf-8")
    admin_router = (ROOT / "admin/src/app/router.tsx").read_text(encoding="utf-8")
    admin_vite = (ROOT / "admin/vite.config.ts").read_text(encoding="utf-8")
    reporter.check(
        "VITE_API_BASE_URL=https://admitly.onrender.com" in admin_example,
        "admin production API URL points to the production backend",
        "admin production API URL is missing or unexpected",
    )
    reporter.check(
        all(route in admin_router for route in ("/privacy", "/refund-policy", "/terms", "/organizer-terms", "/buyer-terms")),
        "admin public legal routes are present",
        "one or more admin public legal routes are missing",
    )
    reporter.check(
        "__ADMITLY_RELEASE__" in admin_vite and "VERCEL_GIT_COMMIT_SHA" in admin_vite,
        "admin build embeds release identity with commit/version fallback",
        "admin release identity build wiring is missing",
    )

    forbidden = ("/payments/dev-test", "Dev Test Checkout", "enableDevTestCheckout")
    found: list[str] = []
    for source_root in (ROOT / "mobile/src", ROOT / "admin/src"):
        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            found.extend(f"{marker} in {path.relative_to(ROOT)}" for marker in forbidden if marker in text)
    reporter.check(
        not found and "enableDevTestCheckout" not in extras,
        "mobile/admin production source exposes no development checkout",
        "development checkout exposure found: " + "; ".join(found),
    )


def _check_production_env(reporter: Reporter, env_file: Path | None) -> None:
    if env_file is None:
        reporter.warning("no production env file supplied; deployed Redis/JWT/MMG/Sentry values were not validated")
        return
    if not env_file.is_file():
        reporter.failed(f"production env file does not exist: {env_file}")
        return

    sys.path.insert(0, str(BACKEND))
    previous_environment = dict(os.environ)
    try:
        from dotenv import dotenv_values
        from pydantic import ValidationError

        values = {key: value for key, value in dotenv_values(env_file).items() if value is not None}
        os.environ.clear()
        os.environ.update(values)
        from app.core.config import Settings

        settings = Settings(_env_file=None, **values)
        reporter.check(
            settings.is_production,
            "supplied environment is production mode",
            "supplied environment file does not set ENV=production",
        )
        reporter.check(
            settings.enable_dev_test_checkout is False,
            "supplied production environment disables development checkout",
            "supplied production environment enables development checkout",
        )
        reporter.check(
            all("localhost" not in origin and "127.0.0.1" not in origin for origin in settings.allowed_cors_origins),
            "supplied production CORS contains no local origins",
            "supplied production CORS contains a local origin",
        )
        if settings.sentry_dsn:
            reporter.passed("backend Sentry is configured (value redacted)")
        else:
            reporter.warning("backend Sentry DSN is absent; startup remains allowed but monitoring will be disabled")
    except ValidationError as exc:
        messages = "; ".join(error["msg"] for error in exc.errors())
        reporter.failed(f"supplied production environment failed startup validation: {messages}")
    finally:
        os.environ.clear()
        os.environ.update(previous_environment)
        if sys.path and sys.path[0] == str(BACKEND):
            sys.path.pop(0)


def _check_git_diff(reporter: Reporter) -> None:
    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    reporter.check(
        result.returncode == 0,
        "git diff --check passes",
        "git diff --check failed: " + (result.stdout + result.stderr).strip(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--production-env-file",
        type=Path,
        help="Optional path to a local production env file. Values are validated but never printed.",
    )
    args = parser.parse_args()

    reporter = Reporter()
    _check_migrations(reporter)
    _check_backend_static(reporter)
    _check_clients(reporter)
    _check_production_env(reporter, args.production_env_file)
    _check_git_diff(reporter)

    print(
        f"SUMMARY: {reporter.passes} PASS, {reporter.warnings} WARNING, {reporter.failures} FAIL"
    )
    return 1 if reporter.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
