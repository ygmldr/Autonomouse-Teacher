"""Run only inside no-credential isolation; never a host-side permission grant."""
from autoteacher_m0.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["smoke", "--mock"]))
