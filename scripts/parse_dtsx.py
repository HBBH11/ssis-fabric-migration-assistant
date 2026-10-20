#!/usr/bin/env python3
"""
parse_dtsx.py

Extracts structural data from an SSIS .dtsx package (control flow tasks,
data flow components, connection managers, variables/parameters,
precedence constraints, and embedded SQL/script metadata) into a single
JSON document that the skill's instructions use to build the Inventory &
Classification report.

Design goals (per skill hard constraints):
- Never raise on malformed/partial input. Every extraction step is wrapped
  so a missing/broken section degrades to an empty result plus a note in
  "parse_warnings", not a crash.
- Output is plain JSON to stdout (or a file with --out) so it's easy for
  the model to read back in and reason over without re-parsing XML itself.
- No external dependencies beyond the Python standard library
  (xml.etree.ElementTree) — this must run offline with no pip installs.

Usage:
    python parse_dtsx.py path/to/package.dtsx
    python parse_dtsx.py path/to/package.dtsx --out package.json
    python parse_dtsx.py path/to/dir_of_packages/ --out portfolio.json
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

NS = {
    "DTS": "www.microsoft.com/SqlServer/Dts",
    "SQLTask": "www.microsoft.com/sqlserver/dts/tasks/sqltask",
    "ScriptTask": "www.microsoft.com/SqlServer/Dts/Tasks/ScriptTask",
}

# CreationName substrings -> normalized task type. Checked with a simple
# "contains" match since real-world CreationName values vary by version
# (e.g. "Microsoft.ExecuteSQLTask" vs "SSIS.ExecuteSQLTask.SR_1_130").
TASK_TYPE_PATTERNS = [
    ("Pipeline", "Data Flow Task"),
    ("ExecuteSQLTask", "Execute SQL Task"),
    ("ScriptTask", "Script Task"),
    ("FOREACHLOOP", "Foreach Loop Container"),
    ("FORLOOP", "For Loop Container"),
    ("SEQUENCE", "Sequence Container"),
    ("FileSystemTask", "File System Task"),
    ("FtpTask", "FTP Task"),
    ("ExecutePackageTask", "Execute Package Task"),
    ("ExecuteProcess", "Execute Process Task"),
    ("SendMailTask", "Send Mail Task"),
    ("DataProfilingTask", "Data Profiling Task"),
    ("WmiEventWatcherTask", "WMI Event Watcher Task"),
    ("AnalysisServicesProcessing", "Analysis Services Processing Task"),
    ("AnalysisServicesExecuteDDL", "Analysis Services Execute DDL Task"),
    ("BulkInsertTask", "Bulk Insert Task"),
    ("TransferSqlServerObjectsTask", "Transfer SQL Server Objects Task"),
    ("CDC", "CDC Task (deprecated)"),
]

# componentClassID substrings -> normalized data flow component type.
DATAFLOW_COMPONENT_PATTERNS = [
    ("OLEDBSource", "OLE DB Source"),
    ("OLEDBDestination", "OLE DB Destination"),
    ("ADONETSource", "ADO.NET Source"),
    ("ADONETDestination", "ADO.NET Destination"),
    ("FlatFileSource", "Flat File Source"),
    ("FlatFileDestination", "Flat File Destination"),
    ("ExcelSource", "Excel Source"),
    ("ExcelDestination", "Excel Destination"),
    ("DataConvert", "Data Conversion"),
    ("DerivedColumn", "Derived Column"),
    ("ConditionalSplit", "Conditional Split"),
    # NOTE: more specific patterns (FuzzyLookup, FuzzyGrouping) must be checked
    # BEFORE the generic "Lookup" pattern — "FuzzyLookup" contains "Lookup" as a
    # substring, so classify()'s first-match-wins logic would otherwise
    # silently misclassify every Fuzzy Lookup as a plain Lookup and suppress
    # the has_fuzzy_lookup_or_grouping risk signal. Caught via eval testing.
    ("FuzzyLookup", "Fuzzy Lookup"),
    ("FuzzyGrouping", "Fuzzy Grouping"),
    ("Lookup", "Lookup"),
    ("Merge", "Merge / Merge Join"),
    ("Aggregate", "Aggregate"),
    ("Sort", "Sort"),
    ("Multicast", "Multicast"),
    ("SCD", "Slowly Changing Dimension (SCD) Wizard"),
    # Same ordering rule: specific CDC component names before the generic
    # "CDC" catch-all, so e.g. "CDCSplit" doesn't fall through to a vaguer label.
    ("CDCSplit", "CDC Splitter (deprecated)"),
    ("AttunityCdc", "Attunity CDC Component (deprecated)"),
    ("CDC", "CDC Component (deprecated)"),
    ("ScriptComponent", "Script Component"),
    ("RowCount", "Row Count"),
]


def classify(value, patterns, default):
    if not value:
        return default
    for pattern, label in patterns:
        if pattern.lower() in value.lower():
            return label
    return default


def local_name(tag):
    """Strip XML namespace braces from a tag, e.g. '{ns}Foo' -> 'Foo'."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def safe_get(el, attr, ns_prefix="DTS"):
    """Attribute lookup that tries the namespaced and bare attribute name."""
    if el is None:
        return None
    val = el.get(f"{{{NS[ns_prefix]}}}{attr}")
    if val is not None:
        return val
    return el.get(attr)


def parse_variables(root, warnings):
    variables = []
    try:
        for var_container in root.iter():
            if local_name(var_container.tag) != "Variables":
                continue
            for var in var_container.findall("DTS:Variable", NS):
                name = safe_get(var, "Name")
                namespace = safe_get(var, "Namespace")
                value_el = var.find("DTS:VariableValue", NS)
                value = value_el.text if value_el is not None else None
                data_type = safe_get(value_el, "DataType") if value_el is not None else None
                variables.append({
                    "name": name,
                    "namespace": namespace,
                    "data_type_code": data_type,
                    "value": value,
                })
    except Exception as e:
        warnings.append(f"Variable parsing failed partway through: {e}")
    return variables


def parse_connection_managers(root, warnings):
    conns = []
    try:
        for cm_container in root.iter():
            if local_name(cm_container.tag) != "ConnectionManagers":
                continue
            for cm in cm_container.findall("DTS:ConnectionManager", NS):
                name = safe_get(cm, "ObjectName")
                creation_name = safe_get(cm, "CreationName")
                conn_string = None
                try:
                    inner = cm.find(".//DTS:ConnectionManager", NS)
                    if inner is not None:
                        conn_string = safe_get(inner, "ConnectionString")
                except Exception:
                    pass
                conns.append({
                    "name": name,
                    "type": creation_name,
                    "connection_string": conn_string,
                    "is_dynamic": bool(
                        conn_string and ("@[" in conn_string or "%" in conn_string)
                    ),
                })
    except Exception as e:
        warnings.append(f"Connection manager parsing failed partway through: {e}")
    return conns


def parse_dataflow_components(pipeline_obj_data, warnings):
    components = []
    try:
        for comp in pipeline_obj_data.iter():
            if local_name(comp.tag) != "component":
                continue
            name = comp.get("name")
            class_id = comp.get("componentClassID")
            components.append({
                "name": name,
                "raw_class_id": class_id,
                "type": classify(class_id, DATAFLOW_COMPONENT_PATTERNS, "Unrecognized component"),
            })
    except Exception as e:
        warnings.append(f"Data flow component parsing failed for one pipeline: {e}")
    return components


def extract_sql_text(executable, warnings):
    try:
        sql_el = executable.find(".//SQLTask:SqlTaskData", NS)
        if sql_el is not None:
            return safe_get(sql_el, "SqlStatementSource", ns_prefix="SQLTask")
    except Exception as e:
        warnings.append(f"SQL text extraction failed for a task: {e}")
    return None


def extract_script_language(executable, warnings):
    try:
        script_el = executable.find(".//ScriptTask:ScriptTaskData", NS)
        if script_el is not None:
            return safe_get(script_el, "ScriptLanguage", ns_prefix="ScriptTask")
    except Exception as e:
        warnings.append(f"Script language extraction failed for a task: {e}")
    return None


def parse_executables(container, warnings, path_prefix=""):
    """
    Recursively walk DTS:Executables, since Sequence/Loop containers nest
    their own child executables. Returns a flat list with a 'parent_path'
    field so the report can reconstruct nesting/containment.
    """
    results = []
    try:
        direct_children = container.find("DTS:Executables", NS)
        if direct_children is None:
            return results
        for ex in direct_children.findall("DTS:Executable", NS):
            obj_name = safe_get(ex, "ObjectName") or "(unnamed)"
            creation_name = safe_get(ex, "CreationName")
            ref_id = safe_get(ex, "refId")
            task_type = classify(creation_name, TASK_TYPE_PATTERNS, creation_name or "Unknown task type")

            entry = {
                "object_name": obj_name,
                "ref_id": ref_id,
                "raw_creation_name": creation_name,
                "task_type": task_type,
                "parent_path": path_prefix,
                "sql_text": None,
                "script_language": None,
                "dataflow_components": [],
            }

            if task_type == "Execute SQL Task":
                entry["sql_text"] = extract_sql_text(ex, warnings)
            elif task_type == "Script Task":
                entry["script_language"] = extract_script_language(ex, warnings)
            elif task_type == "Data Flow Task":
                for obj_data in ex.findall("DTS:ObjectData", NS):
                    entry["dataflow_components"].extend(
                        parse_dataflow_components(obj_data, warnings)
                    )

            results.append(entry)

            # Recurse into nested executables (Sequence/Loop containers).
            child_path = f"{path_prefix}/{obj_name}" if path_prefix else obj_name
            results.extend(parse_executables(ex, warnings, path_prefix=child_path))
    except Exception as e:
        warnings.append(f"Executable tree parsing failed partway through at '{path_prefix}': {e}")
    return results


def parse_precedence_constraints(root, warnings):
    constraints = []
    try:
        for pc_container in root.iter():
            if local_name(pc_container.tag) != "PrecedenceConstraints":
                continue
            for pc in pc_container.findall("DTS:PrecedenceConstraint", NS):
                constraints.append({
                    "from": safe_get(pc, "From"),
                    "to": safe_get(pc, "To"),
                    "value": safe_get(pc, "Value"),  # 0=Success,1=Failure,2=Completion typically
                    "expression": safe_get(pc, "Expression"),
                    "eval_op": safe_get(pc, "EvalOp"),
                })
    except Exception as e:
        warnings.append(f"Precedence constraint parsing failed partway through: {e}")
    return constraints


def parse_dtsx_file(path):
    warnings = []
    result = {
        "source_file": os.path.basename(path),
        "parse_status": "complete",
        "package_name": None,
        "variables": [],
        "connection_managers": [],
        "tasks": [],
        "precedence_constraints": [],
        "parse_warnings": warnings,
    }

    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        result["parse_status"] = "failed"
        warnings.append(f"Could not read file: {e}")
        return result

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        result["parse_status"] = "failed"
        warnings.append(f"XML is not well-formed: {e}. No structural data could be extracted. "
                         f"Recommend opening in a text/XML editor to check for truncation or encoding issues.")
        return result
    except Exception as e:
        result["parse_status"] = "failed"
        warnings.append(f"Unexpected error parsing XML: {e}")
        return result

    result["package_name"] = safe_get(root, "ObjectName") or os.path.splitext(os.path.basename(path))[0]

    result["variables"] = parse_variables(root, warnings)
    result["connection_managers"] = parse_connection_managers(root, warnings)
    result["tasks"] = parse_executables(root, warnings)
    result["precedence_constraints"] = parse_precedence_constraints(root, warnings)

    if warnings:
        result["parse_status"] = "partial"

    # Lightweight signal flags the skill's instructions use directly when
    # scoring risk, so the model doesn't have to re-derive them from the
    # raw task list every time.
    task_types = [t["task_type"] for t in result["tasks"]]
    all_component_types = [
        c["type"] for t in result["tasks"] for c in t["dataflow_components"]
    ]
    result["signals"] = {
        "script_task_count": task_types.count("Script Task"),
        "script_component_count": all_component_types.count("Script Component"),
        "has_fuzzy_lookup_or_grouping": any(
            c in ("Fuzzy Lookup", "Fuzzy Grouping") for c in all_component_types
        ),
        "has_deprecated_cdc": any(
            "deprecated" in t.lower() for t in task_types
        ) or any("deprecated" in c.lower() for c in all_component_types),
        "has_scd_wizard": "Slowly Changing Dimension (SCD) Wizard" in all_component_types,
        "has_execute_process_or_wmi": any(
            t in ("Execute Process Task", "WMI Event Watcher Task") for t in task_types
        ),
        "max_container_nesting_depth": max(
            [t["parent_path"].count("/") + 1 if t["parent_path"] else 0 for t in result["tasks"]],
            default=0,
        ),
        "dynamic_connection_string_count": sum(
            1 for c in result["connection_managers"] if c.get("is_dynamic")
        ),
        "total_dataflow_component_count": len(all_component_types),
        "total_task_count": len(result["tasks"]),
    }

    return result


def collect_dtsx_paths(input_path):
    if os.path.isdir(input_path):
        paths = []
        for root_dir, _, files in os.walk(input_path):
            for fname in files:
                if fname.lower().endswith(".dtsx"):
                    paths.append(os.path.join(root_dir, fname))
        return sorted(paths)
    return [input_path]


def main():
    parser = argparse.ArgumentParser(description="Parse .dtsx SSIS packages into structured JSON.")
    parser.add_argument("input", help="Path to a .dtsx file or a directory containing .dtsx files.")
    parser.add_argument("--out", help="Write JSON output to this file instead of stdout.")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON (default on).")
    args = parser.parse_args()

    paths = collect_dtsx_paths(args.input)
    if not paths:
        print(json.dumps({"error": f"No .dtsx files found at '{args.input}'"}, indent=2))
        sys.exit(1)

    parsed = [parse_dtsx_file(p) for p in paths]
    output = parsed[0] if len(parsed) == 1 and os.path.isfile(args.input) else {"packages": parsed}

    text = json.dumps(output, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {len(paths)} package(s) to {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
