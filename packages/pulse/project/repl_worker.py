"""A watch process that exits when its owning REPL disappears."""

import sys

from pulse.project.cli import main
from pulse.project.guard import parent_guard

if __name__ == "__main__":
    with parent_guard():
        raise SystemExit(main(sys.argv[1:]))
