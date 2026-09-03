"""
Legacy launcher kept for backward compatibility.

The v4 UI implementation lives in ui/app.py.
"""

def main():
    import argparse
    from version import __version__

    parser = argparse.ArgumentParser(description="SE Tactical Command")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--self-test", metavar="REPORT_JSON", help="Verify packaged imports, data and renderer without opening the app")
    args = parser.parse_args()
    if args.self_test:
        from runtime_selftest import run_selftest
        return run_selftest(args.self_test)
    from ui.app import main as run_app
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())

