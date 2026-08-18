#!/usr/bin/env python3
"""
Load environment variables from a .env file and execute a command.
This avoids shell parsing issues with complex values like JSON arrays.
"""

import os
import subprocess
import sys
from pathlib import Path


def load_env_file(env_path: Path) -> dict:
    """Load environment variables from a .env file."""
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, val = line.partition("=")
                if key:
                    env[key.strip()] = val.strip()
    return env


def main():
    if len(sys.argv) < 3:
        print("Usage: load_env.py <env_file> <command> [args...]", file=sys.stderr)
        sys.exit(1)

    env_file = Path(sys.argv[1]).resolve()  # Resolve to absolute path
    command = sys.argv[2:]

    if not env_file.exists():
        print(f"Env file not found: {env_file}", file=sys.stderr)
        sys.exit(1)

    # Load env vars from file
    file_env_vars = load_env_file(env_file)

    # Merge: existing environment takes precedence over file
    # This allows CI to override test defaults (e.g., DATABASE_URL, REDIS_URL)
    merged_env = {**file_env_vars, **os.environ}

    # Execute command with merged environment
    result = subprocess.run(command, env=merged_env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
