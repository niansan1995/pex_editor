#!/usr/bin/env python3
"""在 Excel 可编辑的 CSV 与独立参数 JSON 之间转换。"""

import argparse
import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

HEADER = ("component", "parameter", "type", "typical", "delta_or_percent", "direction")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def number(value):
    """读取有限十进制数，避免二进制浮点误差。"""
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid number: " + str(value)) from None
    if not result.is_finite():
        raise ValueError("Number must be finite: " + str(value))
    return result


def expand(kind, typical, amount, direction):
    """按 CMAX、TYPICAL、CMIN 顺序计算参数。"""
    base = number(typical)
    if kind == "same":
        if amount or direction:
            raise ValueError("same requires only one value")
        return format(base, "f")
    if kind not in ("delta", "ratio") or direction not in ("-+", "+-"):
        raise ValueError("Expected same/delta/ratio and direction -+ or +-")
    step = number(amount.rstrip("%") if kind == "ratio" else amount)
    if step < 0:
        raise ValueError("Delta or percent must be non-negative")
    with localcontext() as context:
        context.prec = max(50, len(base.as_tuple().digits) + len(step.as_tuple().digits)
                           + abs(base.as_tuple().exponent) + abs(step.as_tuple().exponent) + 10)
        if kind == "ratio":
            step = abs(base) * step / 100
        offset = -step if direction == "-+" else step
        return [format(base + offset, "f"), format(base, "f"), format(base - offset, "f")]


def csv_to_json(source, target):
    """完整校验 CSV 后写出参数文件；组件列留空表示全局参数。"""
    data = {"parameters": {}, "components": {}}
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream)
        if next(rows, None) != list(HEADER):
            raise ValueError("Expected CSV header: " + ",".join(HEADER))
        for row_number, row in enumerate(rows, 2):
            if not any(value.strip() for value in row):
                continue
            try:
                if not 4 <= len(row) <= 6:
                    raise ValueError("Expected 4 to 6 columns")
                component, name, kind, typical, amount, direction = [value.strip() for value in row] + [""] * (6 - len(row))
                if not NAME.fullmatch(name) or (component and not NAME.fullmatch(component)):
                    raise ValueError("Expected separate component and parameter names")
                group = data["components"].setdefault(component, {}) if component else data["parameters"]
                if name in group:
                    raise ValueError("Duplicate parameter: " + (component or "global") + "/" + name)
                group[name] = expand(kind.lower(), typical, amount, direction)
            except ValueError as error:
                raise ValueError("CSV row " + str(row_number) + ": " + str(error)) from None
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def json_to_csv(source, target):
    """单值导出 same，对称三值导出 delta，不能还原原始类型。"""
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    rows = [HEADER]
    groups = [("", data.get("parameters", {}))]
    groups.extend(data.get("components", {}).items())
    for component, parameters in groups:
        for name, value in parameters.items():
            if not isinstance(value, list):
                rows.append((component, name, "same", format(number(value), "f"), "", ""))
                continue
            if len(value) != 3:
                raise ValueError("Expected three corners: " + (component or "global") + "/" + name)
            high, typical, low = map(number, value)
            if high + low != 2 * typical:
                raise ValueError("Asymmetric corners cannot be exported: " + (component or "global") + "/" + name)
            rows.append((component, name, "delta", format(typical, "f"),
                         format(abs(high - typical), "f"), "-+" if high <= typical else "+-"))
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)


def main():
    """提供生成 JSON 和导出 CSV 的命令行入口。"""
    parser = argparse.ArgumentParser(description="Edit parameters in Excel CSV and generate parameter JSON.")
    parser.add_argument("command", choices=("to-json", "to-csv"))
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        if args.source.resolve() == args.target.resolve():
            raise ValueError("Source and target must differ")
        action = csv_to_json if args.command == "to-json" else json_to_csv
        action(args.source, args.target)
    except (OSError, ValueError, csv.Error) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    print("Generated: " + str(args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
