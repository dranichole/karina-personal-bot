"""Karina local chatbot for desktop commands."""

from __future__ import annotations

from karina_core import KarinaSession, get_response
from llm import ensure_local_llm


def main() -> int:
    print("Karina: your local desktop agent")
    print("Type commands like 'open notepad', 'launch chrome', or 'list apps'.")
    print("Type 'help' for more commands, 'exit' to quit.")
    print("Starting local model if needed...")

    def progress(message: str) -> None:
        print(f"Karina: {message}")

    available, status = ensure_local_llm(progress=progress)
    print(status)
    print()
    session = KarinaSession()

    while True:
        try:
            text = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            return 0

        if not text:
            continue

        response = get_response(text, session)
        print(f"Karina: {response.text}")

        if response.should_close:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
