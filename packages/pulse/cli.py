"""Public command entry point; the existing lab interface remains available."""

import argparse
import sys
from importlib.metadata import version


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    from pulse.project.cli import COMMANDS

    if arguments and arguments[0].lower() in COMMANDS:
        from pulse.project.cli import main as project_main

        return project_main([arguments[0].lower(), *arguments[1:]])
    if arguments and arguments[0].lower() == "lab":
        from pulse.lab.cli import main as lab_main

        return lab_main(["lab", *arguments[1:]])
    parser = argparse.ArgumentParser(
        prog="pulse", description="Evidence-driven recovery for local infrastructure"
    )
    parser.add_argument("--version", action="version", version="Pulse " + version("pulse-sre"))
    commands = parser.add_subparsers(dest="command")
    repl = commands.add_parser("repl", help="Open a repository or the interactive product demo")
    repl.add_argument("repo", nargs="?")
    for name in sorted(COMMANDS):
        commands.add_parser(name, help=f"Local repository {name}; run pulse {name} --help")
    commands.add_parser("lab", help="Run advanced incident-lab commands")
    if arguments:
        arguments[0] = arguments[0].lower()
    options = parser.parse_args(arguments)
    if options.command == "repl":
        from pulse.repl import run

        return run(options.repo) if options.repo else run()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
