#!/usr/bin/env python3
import os
import sys
import tkinter as tk
from tkinter import simpledialog


def main() -> int:
    prompt = "Administrator password"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        prompt = sys.argv[1].strip()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    password = simpledialog.askstring(
        "BESTT",
        prompt,
        show="*",
        parent=root,
    )
    root.destroy()

    if password is None:
        return 1

    os.write(sys.stdout.fileno(), password.encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
