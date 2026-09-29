"""Quản lý prompt `day13-chat` trong project Langfuse cá nhân.

    python scripts/manage_prompts.py status
    python scripts/manage_prompts.py create      # v1 (baseline, production) + v2 (candidate)
    python scripts/manage_prompts.py promote     # production -> version candidate
    python scripts/manage_prompts.py rollback    # production -> version baseline
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

PROMPT_V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
PROMPT_V2 = (
    "Feature={{feature}}\n"
    "Docs={{docs}}\n"
    "Question={{message}}\n"
    "Answer in at most 3 short sentences, using only the docs above."
)


def _versions(client, name: str) -> dict[str, int]:
    """Map label -> version for the labels this lab uses."""
    labels = {}
    for label in ("baseline", "candidate", "production"):
        try:
            prompt = client.get_prompt(name, label=label, type="text", cache_ttl_seconds=0)
            labels[label] = prompt.version
        except Exception:
            labels[label] = None
    return labels


def _print_status(client, name: str) -> None:
    for label, version in _versions(client, name).items():
        print(f"  {label:<10} -> version {version}")


def main() -> None:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "create", "promote", "rollback"])
    args = parser.parse_args()

    from langfuse import get_client

    client = get_client()
    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

    if args.action == "create":
        existing = _versions(client, name)
        if existing["baseline"] or existing["candidate"]:
            print(f"Prompt '{name}' đã có baseline/candidate, không tạo lại.")
        else:
            v1 = client.create_prompt(
                name=name,
                prompt=PROMPT_V1,
                labels=["baseline", "production"],
                type="text",
                commit_message="v1: baseline template",
            )
            v2 = client.create_prompt(
                name=name,
                prompt=PROMPT_V2,
                labels=["candidate"],
                type="text",
                commit_message="v2: limit answer to 3 short sentences",
            )
            print(f"Đã tạo version {v1.version} (baseline, production) và {v2.version} (candidate).")
    elif args.action in ("promote", "rollback"):
        source_label = "candidate" if args.action == "promote" else "baseline"
        target = _versions(client, name)[source_label]
        if target is None:
            sys.exit(f"Không tìm thấy label '{source_label}'. Chạy 'create' trước.")
        # update_prompt thêm label vào version đích; Langfuse tự gỡ label khỏi version cũ.
        client.update_prompt(name=name, version=target, new_labels=["production"])
        print(f"{args.action}: production -> version {target}")

    print(f"Prompt '{name}':")
    _print_status(client, name)
    client.flush()


if __name__ == "__main__":
    main()
