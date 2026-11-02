from __future__ import annotations

import sys

if len(sys.argv) > 1 and sys.argv[1] == "whatsapp":
    from app.cli.whatsapp import main as whatsapp_main

    # Forward remaining arguments
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    whatsapp_main()
else:
    print("Usage: python -m app.cli <command>")
    print("Available commands: whatsapp")
    sys.exit(1)
