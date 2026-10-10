"""Public command entry point; the existing lab interface remains available."""

import argparse
import sys
from importlib.metadata import version


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0].lower() == "lab":
        from pulse.lab.cli import main as lab_main

        return lab_main(["lab", *arguments[1:]])
    parser = argparse.ArgumentParser(
        prog="pulse", description="Evidence-driven recovery for local infrastructure"
    )
    parser.add_argument("--version", action="version", version="Pulse " + version("pulse-sre"))
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("repl", help="Open the interactive product demo and local lab controls")
    commands.add_parser("lab", help="Run advanced incident-lab commands")
    if arguments:
        arguments[0] = arguments[0].lower()
    options = parser.parse_args(arguments)
    if options.command == "repl":
        from pulse.repl import run

        return run()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
