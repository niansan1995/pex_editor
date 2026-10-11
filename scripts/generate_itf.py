#!/usr/bin/env python3
"""按 metal option 的层序组合模板，生成各 corner 的 ITF 文件。"""

import argparse
import json
import re
import sys
from pathlib import Path

VARIABLE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
OUTPUT_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")
DEFAULT_NAMING = {
    "metal": "metal{{ MID }}",
    "pad": "ALPA",
    "via": "V{{ VIA_ID }}",
    "dielectric": "ILD{{ DIELECTRIC_ID }}",
}
CORNERS = ("CMAX", "TYPICAL", "CMIN")
RESERVED = {
    "CORNER", "METAL_OPTION", "COMPONENT", "LAYER", "LAYER_ID",
    "MID", "PAD_ID", "VIA_ID", "DIELECTRIC_ID",
    "PREVIOUS_LAYER", "NEXT_LAYER", "LOWER_LAYER", "UPPER_LAYER",
}


def render(template, values):
    """仅替换变量，不执行表达式，也不改变模板其余内容。"""
    missing = sorted(set(VARIABLE.findall(template)) - values.keys())
    if missing:
        raise ValueError("Missing template variables: " + ", ".join(missing))
    result = VARIABLE.sub(lambda match: str(values[match.group(1)]), template)
    if "{{" in result or "}}" in result:
        raise ValueError("Unsupported or unresolved template placeholder")
    return result


def resolve_values(parameters, corner, label):
    """单值用于所有 corner，三项列表按 CMAX、TYPICAL、CMIN 取值。"""
    if not isinstance(parameters, dict):
        raise ValueError(label + " must be an object")
    values = {}
    for name, value in parameters.items():
        if not NAME.fullmatch(name) or name in RESERVED:
            raise ValueError("Invalid or reserved parameter name: " + name)
        candidates = value if isinstance(value, list) else [value]
        if isinstance(value, list) and len(value) != len(CORNERS):
            raise ValueError("Corner list must contain [CMAX, TYPICAL, CMIN]: " + name)
        if any(isinstance(item, bool) or not isinstance(item, (str, int, float)) for item in candidates):
            raise ValueError("Parameter must be a string, number or three-value list: " + name)
        values[name] = candidates[CORNERS.index(corner)] if isinstance(value, list) else value
    return values


def read_config(path):
    """读取支持 BOM 的 JSON 对象。"""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be an object: " + str(path))
    return data


def select_names(items, selected, label):
    """选择全部或指定名称，并限制输出目录和文件名。"""
    if not isinstance(items, dict) or not items:
        raise ValueError(label + " must be a non-empty object")
    names = list(items) if selected == "all" else [selected]
    for name in names:
        if not OUTPUT_NAME.fullmatch(name) or name == "all":
            raise ValueError("Invalid or reserved " + label + " name: " + name)
        if name not in items:
            raise ValueError("Unknown " + label + ": " + name + "; available: " + ", ".join(items))
    return names


def instantiate_layers(layers, components, naming):
    """从高到低实例化金属组，按显式导体序号连接末尾的通孔。"""
    if not isinstance(layers, list) or not layers:
        raise ValueError("Metal option must contain a non-empty layer array")
    entries = []
    via_started = False
    for entry in layers:
        entry = {"component": entry} if isinstance(entry, str) else entry
        if not isinstance(entry, dict) or not isinstance(entry.get("component"), str):
            raise ValueError("Layer must be a component name or an object with component")
        component = components.get(entry["component"])
        if not isinstance(component, dict) or component.get("kind") not in DEFAULT_NAMING:
            raise ValueError("Unknown component or invalid kind: " + entry["component"])
        if component["kind"] == "via":
            via_started = True
        elif via_started:
            raise ValueError("All via components must follow the stack components")
        entries.append((entry, component))
    metal_count = sum(component["kind"] == "metal" for _, component in entries)
    counters = dict.fromkeys(DEFAULT_NAMING, 0)
    instances = []
    names = set()
    for index, (entry, component) in enumerate(entries):
        kind = component["kind"]
        counters[kind] += 1
        context = {"COMPONENT": entry["component"], "LAYER_ID": index + 1}
        if kind == "metal":
            context["MID"] = metal_count - counters[kind] + 1
        elif kind == "via":
            connect = entry.get("connect")
            if (not isinstance(connect, list) or len(connect) != 2
                    or any(type(item) is not int for item in connect)):
                raise ValueError("Via connect must be [lower_conductor_number, upper_conductor_number]")
            context["VIA_ID"] = connect[0]
        else:
            context[kind.upper() + "_ID"] = counters[kind]
        pattern = entry.get("name", component.get("name", naming[kind]))
        if not isinstance(pattern, str):
            raise ValueError("Layer name pattern must be a string")
        name = render(pattern, context)
        if not NAME.fullmatch(name) or name in names:
            raise ValueError("Invalid or duplicate layer name: " + name)
        names.add(name)
        context["LAYER"] = name
        instances.append((component, context))
    # 导体连接序号按从低到高排列，包含顶端 ALPA，不依赖输出名称。
    conductors = [context for component, context in reversed(instances)
                  if component["kind"] in ("metal", "pad")]
    for index, (component, context) in enumerate(instances):
        context["PREVIOUS_LAYER"] = instances[index - 1][1]["LAYER"] if index else ""
        context["NEXT_LAYER"] = instances[index + 1][1]["LAYER"] if index + 1 < len(instances) else ""
        if component["kind"] == "via":
            lower, upper = entries[index][0]["connect"]
            if not 1 <= lower < upper <= len(conductors):
                raise ValueError("Via connect references invalid conductor numbers: " + context["LAYER"])
            context["LOWER_LAYER"] = conductors[lower - 1]["LAYER"]
            context["UPPER_LAYER"] = conductors[upper - 1]["LAYER"]
    return instances


def generate(option_path, output_dir, selected="all", selected_option="all"):
    """按配置顺序拼接片段，全部目标渲染成功后再写出文件。"""
    options = read_config(option_path)
    selected = selected.upper() if selected.lower() != "all" else "all"
    corner_names = select_names(dict.fromkeys(CORNERS), selected, "corner")
    metal_options = options.get("metal_options")
    option_names = select_names(metal_options, selected_option, "metal option")
    components = options.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError("components must be a non-empty object")
    parameter_path = None
    if "parameter_file" in options:
        filename = options["parameter_file"]
        if not isinstance(filename, str) or not filename:
            raise ValueError("parameter_file must be a non-empty string")
        parameter_path = (option_path.parent / filename).resolve()
        external = read_config(parameter_path)
        global_parameters = external.get("parameters", {})
        component_parameters = external.get("components", {})
        if not isinstance(global_parameters, dict) or not isinstance(component_parameters, dict):
            raise ValueError("Parameter file must contain parameters and components objects")
        # 保留内联参数作为显式覆盖，便于独立配置和已有调用继续使用。
        options["parameters"] = dict(global_parameters, **options.get("parameters", {}))
        for name, parameters in component_parameters.items():
            if name not in components:
                raise ValueError("Unknown component in parameter file: " + name)
            if not isinstance(parameters, dict):
                raise ValueError("Component parameters must be an object: " + name)
            components[name]["parameters"] = dict(parameters, **components[name].get("parameters", {}))
    naming = options.get("naming", {})
    if not isinstance(naming, dict) or any(key not in DEFAULT_NAMING for key in naming):
        raise ValueError("naming must be an object with metal, pad, via or dielectric keys")
    naming = dict(DEFAULT_NAMING, **naming)
    suffixes = options.get("suffix_templates", [])
    via_templates = options.get("via_templates", [])
    if not isinstance(suffixes, list) or not isinstance(via_templates, list):
        raise ValueError("suffix_templates and via_templates must be arrays")
    templates = {}
    inputs = {option_path.resolve()}
    if parameter_path is not None:
        inputs.add(parameter_path)

    def template_text(filename):
        """相对模板路径以 metal_option.json 所在目录为基准。"""
        if not isinstance(filename, str) or not filename:
            raise ValueError("Template path must be a non-empty string")
        path = (option_path.parent / filename).resolve()
        inputs.add(path)
        if path not in templates:
            with path.open(encoding="utf-8-sig", newline="") as source:
                templates[path] = source.read()
        return templates[path]

    rendered = []
    for option in option_names:
        instances = instantiate_layers(metal_options[option], components, naming)
        for corner in corner_names:
            values = resolve_values(options.get("parameters", {}), corner, "global parameters")
            values.update(CORNER=corner, METAL_OPTION=option)
            pieces = [render(template_text(options.get("header_template")), values)]
            suffix_written = False
            for component, context in instances:
                if component["kind"] == "via" and not suffix_written:
                    pieces.extend(render(template_text(filename), values) for filename in suffixes)
                    suffix_written = True
                local = dict(values)
                local.update(resolve_values(component.get("parameters", {}), corner, context["COMPONENT"]))
                local.update(context)
                pieces.append(render(template_text(component.get("template")), local))
            if not suffix_written:
                pieces.extend(render(template_text(filename), values) for filename in suffixes)
            pieces.extend(render(template_text(filename), values) for filename in via_templates)
            target = output_dir / option / (corner + ".itf")
            rendered.append((target, "".join(pieces)))
    for target, _ in rendered:
        if target.resolve() in inputs:
            raise ValueError("Output would overwrite an input file: " + str(target))
    for target, content in rendered:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as output:
            output.write(content)
        print("Generated: " + str(target))
    return [target for target, _ in rendered]


def main():
    """提供命令行入口，默认生成全部组合和全部 corner。"""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate PEX corner ITF files from metal option templates.")
    parser.add_argument("--metal-options", type=Path, default=root / "metal_option.json")
    parser.add_argument("--output-dir", type=Path, default=root / "build")
    parser.add_argument("--corner", default="all", help="CMAX, TYPICAL, CMIN or all (case-insensitive; default: all)")
    parser.add_argument("--metal-option", default="all", help="Metal option name or all (default: all)")
    args = parser.parse_args()
    try:
        generate(args.metal_options, args.output_dir, args.corner, args.metal_option)
    except (OSError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
