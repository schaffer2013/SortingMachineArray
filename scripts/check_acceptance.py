from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.application.acceptance_envelope import evaluate_acceptance_envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the current pre-hardware acceptance envelope checks.")
    parser.add_argument("--json-out", default="data/recognition_reports/acceptance_envelope.json")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary benchmark output directory.")
    args = parser.parse_args()

    temp_root = PROJECT_ROOT / ".tmp_acceptance"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    command_results: list[dict[str, object]] = []
    try:
        pytest_result = _run_command(
            [sys.executable, "-m", "pytest", "tests"],
            command_results,
            label="pytest",
            cwd=PROJECT_ROOT,
        )

        sim_truth_path = temp_root / "sim_truth.json"
        _run_command(
            [sys.executable, "scripts/benchmark_recognizer.py", "--backend", "sim_truth", "--json-out", str(sim_truth_path)],
            command_results,
            label="sim_truth_benchmark",
            cwd=PROJECT_ROOT,
        )

        fuzzy_greenfield_path = temp_root / "fuzzy_greenfield.json"
        _run_command(
            [sys.executable, "scripts/benchmark_recognizer.py", "--backend", "fuzzy_enigma", "--card-engine-mode", "greenfield", "--json-out", str(fuzzy_greenfield_path)],
            command_results,
            label="fuzzy_greenfield_benchmark",
            cwd=PROJECT_ROOT,
        )

        fuzzy_small_pool_path = temp_root / "fuzzy_small_pool_expected.json"
        _run_command(
            [
                sys.executable,
                "scripts/benchmark_recognizer.py",
                "--backend",
                "fuzzy_enigma",
                "--card-engine-mode",
                "small_pool",
                "--use-expected-label",
                "--json-out",
                str(fuzzy_small_pool_path),
            ],
            command_results,
            label="fuzzy_small_pool_expected_benchmark",
            cwd=PROJECT_ROOT,
        )

        fuzzy_golden_path = temp_root / "fuzzy_golden_small_pool.json"
        _run_command(
            [
                sys.executable,
                "scripts/run_golden_frames.py",
                "--backend",
                "fuzzy_enigma",
                "--card-engine-mode",
                "small_pool",
                "--use-expected-label",
                "--json-out",
                str(fuzzy_golden_path),
            ],
            command_results,
            label="fuzzy_golden_small_pool",
            cwd=PROJECT_ROOT,
        )

        envelope = evaluate_acceptance_envelope(
            pytest_passed=pytest_result.returncode == 0,
            sim_truth_summary=_read_json(sim_truth_path),
            fuzzy_greenfield_summary=_read_json(fuzzy_greenfield_path),
            fuzzy_small_pool_summary=_read_json(fuzzy_small_pool_path),
            fuzzy_golden_small_pool_summary=_read_json(fuzzy_golden_path),
        )

        output_path = PROJECT_ROOT / args.json_out
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = envelope.to_dict()
        payload["commands"] = command_results
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        print(f"overall_passed={envelope.overall_passed}")
        for gate in envelope.gates:
            print(f"{gate.name}={'PASS' if gate.passed else 'FAIL'}")
        print(f"json_out={output_path}")
        return 0 if envelope.overall_passed else 1
    finally:
        if not args.keep_temp and temp_root.exists():
            shutil.rmtree(temp_root)


def _run_command(argv: list[str], command_results: list[dict[str, object]], *, label: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    command_results.append(
        {
            "label": label,
            "argv": argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
