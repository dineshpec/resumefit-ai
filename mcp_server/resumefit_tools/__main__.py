"""Entry point: `python -m resumefit_tools [--host HOST] [--port PORT]`.

Start the service through this module, not `-m resumefit_tools.server`. Extraction
workers use the `spawn` start method, which re-runs the parent's main module in
every child unless that module is a package `__main__`. Starting here keeps
FastMCP and uvicorn out of each worker, so the worker's 256 MB address-space
limit is left for the parser.
"""

from resumefit_tools.server import main

if __name__ == "__main__":
    main()
