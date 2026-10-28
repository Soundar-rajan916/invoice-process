from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def check_thresholds(
    report_data: dict[str, Any],
    thresholds: dict[str, Any],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    accuracies = report_data.get("accuracies", {})
    flags = report_data.get("flags", {})
    false_alarm_rate = report_data.get("clean_invoice_false_alarm_rate", 0.0)

    # 1. Check accuracies
    th_acc = thresholds.get("accuracies", {})
    for field_name, min_val in th_acc.items():
        actual_val = accuracies.get(field_name, 0.0)
        if actual_val < min_val:
            failures.append(
                f"[FAIL] Accuracy for '{field_name}': actual {actual_val * 100:.2f}% < required {min_val * 100:.2f}%"
            )
        else:
            print(
                f"[PASS] Accuracy for '{field_name}': {actual_val * 100:.2f}% >= {min_val * 100:.2f}%"
            )

    # 2. Check flag recalls
    th_flags = thresholds.get("flags", {})
    for flag_code, f_rules in th_flags.items():
        min_recall = f_rules.get("min_recall", 1.0)
        flag_data = flags.get(flag_code, {})
        actual_recall = flag_data.get("recall", 0.0)
        if actual_recall < min_recall:
            failures.append(
                f"[FAIL] Recall for flag '{flag_code}': actual {actual_recall * 100:.2f}% < required {min_recall * 100:.2f}%"
            )
        else:
            print(
                f"[PASS] Recall for flag '{flag_code}': {actual_recall * 100:.2f}% >= {min_recall * 100:.2f}%"
            )

    # 3. Check false alarm rate
    th_fa = thresholds.get("false_alarm", {})
    max_fa = th_fa.get("max_clean_invoice_rate", 0.02)
    if false_alarm_rate > max_fa:
        failures.append(
            f"[FAIL] Clean invoice false alarm rate: actual {false_alarm_rate * 100:.2f}% > allowed {max_fa * 100:.2f}%"
        )
    else:
        print(
            f"[PASS] Clean invoice false alarm rate: {false_alarm_rate * 100:.2f}% <= {max_fa * 100:.2f}%"
        )

    passed = len(failures) == 0
    return passed, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify evaluation metrics against thresholds")
    parser.add_argument(
        "--report", type=str, default="eval/reports/report.json", help="Path to report.json"
    )
    parser.add_argument(
        "--thresholds", type=str, default="eval/thresholds.yaml", help="Path to thresholds.yaml"
    )

    args = parser.parse_args()

    report_path = Path(args.report)
    thresholds_path = Path(args.thresholds)

    if not report_path.exists():
        print(
            f"Error: report file {report_path} does not exist. Run eval.run first.", file=sys.stderr
        )
        sys.exit(1)

    if not thresholds_path.exists():
        print(f"Error: thresholds file {thresholds_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    with report_path.open("r", encoding="utf-8") as f:
        report_data = json.load(f)

    with thresholds_path.open("r", encoding="utf-8") as f:
        thresholds_data = yaml.safe_load(f)

    print("Checking evaluation report against thresholds...\n")
    passed, failures = check_thresholds(report_data, thresholds_data)

    if not passed:
        print("\nThreshold verification FAILED:")
        for fail_msg in failures:
            print(f"  {fail_msg}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nAll threshold checks PASSED! CI gate is green.")
        sys.exit(0)


if __name__ == "__main__":
    main()
