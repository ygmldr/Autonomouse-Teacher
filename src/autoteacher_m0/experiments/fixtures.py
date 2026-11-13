"""Load exactly the public fictional Mock fixtures; never private datasets."""
import json
from importlib.resources import files
from pathlib import Path
from autoteacher_m0.evaluation.contracts import EvalContract


def load_cases(path: Path | str | None = None) -> list[EvalContract]:
    if path is not None:
        source = Path(path)
    else:
        packaged = files("autoteacher_m0").joinpath("data", "teacher_cases.jsonl")
        source = (packaged if packaged.is_file() else
                  Path(__file__).resolve().parents[3] / "fixtures" / "teacher_cases.jsonl")
    with source.open(encoding="utf-8") as stream:
        cases = [EvalContract.from_dict(json.loads(line)) for line in stream if line.strip()]
    if len(cases) != 20 or len({case.case_id for case in cases}) != 20:
        raise ValueError("public Mock suite requires exactly 20 unique cases")
    counts = {split: sum(case.split == split for case in cases)
              for split in ("development", "simulated_holdout")}
    if counts != {"development": 12, "simulated_holdout": 8}:
        raise ValueError("public Mock split must be 12 development / 8 simulated holdout")
    categories = {category: sum(case.category == category for case in cases)
                  for category in {case.category for case in cases}}
    if categories != {"monotonicity": 5, "boundaries": 5, "complexity_prerequisites": 4,
                      "code_overflow": 4, "insufficient_information": 2}:
        raise ValueError("unexpected public Mock category distribution")
    return cases
