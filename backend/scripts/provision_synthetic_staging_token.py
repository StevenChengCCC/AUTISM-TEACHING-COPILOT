#!/usr/bin/env python3
"""Provision an isolated synthetic Cognito test identity and write an ID token.

The password exists only in process memory. The token file is created with
owner-only permissions and the command never prints credentials or token data.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import subprocess
import sys
from pathlib import Path

def _password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_=+"
    return "Atc!" + "".join(secrets.choice(alphabet) for _ in range(36)) + "9z"


def _write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, value.encode("utf-8"))
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _aws(args: argparse.Namespace, *command: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "AWS_PAGER": ""}
    return subprocess.run(
        [
            args.aws_cli,
            *command,
            "--profile",
            args.profile,
            "--region",
            args.region,
            "--output",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _require_success(result: subprocess.CompletedProcess[str], operation: str) -> str:
    if result.returncode != 0:
        error_code = "AWSServiceError"
        for candidate in (
            "NotAuthorizedException",
            "InvalidParameterException",
            "TooManyRequestsException",
            "UserNotFoundException",
        ):
            if candidate in result.stderr:
                error_code = candidate
                break
        raise RuntimeError(f"{operation} returned {error_code}")
    return result.stdout


def provision(args: argparse.Namespace) -> str:
    password = _password()
    attributes = (
        f"Name=email,Value={args.username}",
        "Name=email_verified,Value=true",
        "Name=name,Value=Synthetic Quality Teacher",
        f"Name=custom:organization_id,Value={args.organization_id}",
    )
    existing = _aws(
        args,
        "cognito-idp",
        "admin-get-user",
        "--user-pool-id",
        args.user_pool_id,
        "--username",
        args.username,
    )
    if existing.returncode == 0:
        _require_success(
            _aws(
                args,
                "cognito-idp",
                "admin-update-user-attributes",
                "--user-pool-id",
                args.user_pool_id,
                "--username",
                args.username,
                "--user-attributes",
                *attributes,
            ),
            "admin-update-user-attributes",
        )
    elif "UserNotFoundException" in existing.stderr:
        _require_success(
            _aws(
                args,
                "cognito-idp",
                "admin-create-user",
                "--user-pool-id",
                args.user_pool_id,
                "--username",
                args.username,
                "--user-attributes",
                *attributes,
                "--message-action",
                "SUPPRESS",
            ),
            "admin-create-user",
        )
    else:
        _require_success(existing, "admin-get-user")
    _require_success(
        _aws(
            args,
            "cognito-idp",
            "admin-set-user-password",
            "--user-pool-id",
            args.user_pool_id,
            "--username",
            args.username,
            "--password",
            password,
            "--permanent",
        ),
        "admin-set-user-password",
    )
    auth_parameters = json.dumps(
        {
            "USERNAME": args.username,
            "PASSWORD": password,
            "PREFERRED_CHALLENGE": "PASSWORD",
        }
    )
    auth = json.loads(
        _require_success(
            _aws(
                args,
                "cognito-idp",
                "initiate-auth",
                "--client-id",
                args.client_id,
                "--auth-flow",
                "USER_AUTH",
                "--auth-parameters",
                auth_parameters,
            ),
            "initiate-auth",
        )
    )
    result = auth.get("AuthenticationResult")
    if not result:
        raise RuntimeError(
            f"Cognito returned unsupported challenge {auth.get('ChallengeName', 'unknown')}"
        )
    token = result.get("IdToken")
    if not token:
        raise RuntimeError("Cognito did not return an ID token")
    _write_private(args.token_file, token)
    return str(auth.get("ChallengeName") or "authenticated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="agent-toolkit")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--aws-cli", default="/Users/chengshensihan/.local/bin/aws")
    parser.add_argument("--user-pool-id", default="us-east-1_xkIC5T6Wm")
    parser.add_argument("--client-id", default="68vqua31osg5polou9utg77tpi")
    parser.add_argument(
        "--username", default="synthetic-quality-loop@autismteachingcopilot.invalid"
    )
    parser.add_argument("--organization-id", default="synthetic-quality-lab")
    parser.add_argument("--token-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = provision(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Synthetic Cognito identity is {status}; private token file created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
