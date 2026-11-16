from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_controller as tc


def main() -> int:
    root = Path(sys.argv[1])
    controller, broker, fake, attempts = tc._controller(root)
    try:
        tc._frames(controller, tc._payload())
    finally:
        broker.close()
        fake.close()
        attempts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
