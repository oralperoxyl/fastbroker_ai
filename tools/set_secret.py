import getpass
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/set_secret.py NAME")

    name = sys.argv[1]
    value = getpass.getpass(f"Paste {name} and press Enter: ").strip()
    if not value:
        raise SystemExit("Value is empty.")

    env_path = Path(".env")
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = []
    changed = False

    for line in lines:
        if line.startswith(f"{name}="):
            updated.append(f"{name}={value}")
            changed = True
        else:
            updated.append(line)

    if not changed:
        updated.append(f"{name}={value}")

    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print(f"{name} saved.")


if __name__ == "__main__":
    main()
