"""Create initial pilot accounts and a protected credentials handoff on the VPS."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--basic-password-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    accounts = [
        {"email": "admin@suite-s1.denjik.by", "role": "admin", "display_name": "Pilot Admin"},
        {"email": "pilot@suite-s1.denjik.by", "role": "user", "display_name": "Pilot Seller"},
    ]
    for account in accounts:
        account["password"] = secrets.token_urlsafe(24)
    credentials = {
        "url": "https://suite-s1.denjik.by",
        "basic_auth": {
            "username": "pilot",
            "password": args.basic_password_file.read_text().strip(),
        },
        "accounts": accounts,
    }
    # Persist first so an interrupted account creation never loses a password.
    with args.output.open("x", encoding="utf-8") as output:
        os.chmod(args.output, 0o600)
        json.dump(credentials, output, indent=2)
        output.write("\n")
    for account in accounts:
        subprocess.run(
            [
                "docker", "compose", "exec", "-T", "api", "python", "-m", "app.cli",
                "create-user", "--email", account["email"], "--display-name", account["display_name"],
                "--role", account["role"], "--password-stdin",
            ],
            cwd=args.app_dir,
            input=account["password"] + "\n",
            text=True,
            check=True,
        )
    print(f"Created two pilot accounts. Protected credentials: {args.output}")


if __name__ == "__main__":
    main()
