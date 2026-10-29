"""Derive the small production resource from the immutable audited catalogue.

Run from any directory with Python; no network, browser, or Maximo dependency.
Only RFN-20 / P-RFN-139 / C-RFN-062 / S-RFN-263 is excluded. Shared groups
are cloned along that context, so other classes and parents remain unchanged.
"""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/catalogos/anomalias/2026-10-28/catalogo_anomalias.json"
DESTINATION = ROOT / "resources/failure_catalog.json"


def prepare_catalog(source):
    """Pure transformation; original group indices remain stable after pruning."""
    groups = {}
    for reference, options in source["option_sets"].items():
        def leaf_identity(item):
            return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

        counts = Counter(leaf_identity(item) for item in options if not item.get("children_ref"))
        seen_leaves = set()
        prepared = []
        for index, item in enumerate(options):
            identity = leaf_identity(item)
            if not item.get("children_ref"):
                if identity in seen_leaves:
                    continue
                seen_leaves.add(identity)
            entry = {"key": f"{reference}:{index}", **deepcopy(item)}
            if not item.get("children_ref") and counts[identity] > 1:
                entry["allow_duplicate"] = True
            prepared.append(entry)
        groups[reference] = prepared
    classes = [{"key": f"{item['organization']}|{item['code']}", **deepcopy(item)}
               for item in source["classes"]]
    target = next(item for item in classes if item["key"] == "TRANSPORTES|RFN-20")
    original_root = target["options_ref"]
    root_clone = original_root + "_rfn20_confirmed"
    groups[root_clone] = deepcopy(groups[original_root])
    # Keys in clones must belong to the clone, not to the original shared set.
    for entry in groups[root_clone]:
        entry["key"] = root_clone + ":" + entry["key"].rsplit(":", 1)[1]
    target["options_ref"] = root_clone
    problem = next(item for item in groups[root_clone] if item["code"] == "P-RFN-139")
    original_causes = problem["children_ref"]
    causes_clone = original_causes + "_rfn20_p139_confirmed"
    causes = []
    confirmed = 0
    excluded = 0
    for original in groups[original_causes]:
        item = deepcopy(original)
        item["key"] = causes_clone + ":" + item["key"].rsplit(":", 1)[1]
        if item["type"] == "CAUSE" and item["code"] == "C-RFN-062":
            successors = groups[item["children_ref"]]
            codes = {child["code"] for child in successors}
            if codes == {"S-RFN-263"}:
                # Drop this occurrence entirely: pruning must not create a
                # terminal CAUSE that never existed in the audited catalogue.
                excluded += 1
                continue
            if codes != {"S-RFN-262"}:
                raise ValueError("La rama C-RFN-062 auditada ha cambiado; revisar la exclusión contextual.")
            item["allow_duplicate"] = True
            confirmed += 1
        causes.append(item)
    if (excluded, confirmed) != (1, 1):
        raise ValueError("No se encontró exactamente la discrepancia RFN-20/P-RFN-139 auditada.")
    groups[causes_clone] = causes
    problem["children_ref"] = causes_clone
    # Keep compact shared groups, but omit any group unreachable after pruning.
    reachable = set()

    def visit(reference):
        if reference in reachable:
            return
        reachable.add(reference)
        for item in groups[reference]:
            if item.get("children_ref"):
                visit(item["children_ref"])

    for item in classes:
        visit(item["options_ref"])
    return {"version": 1, "classes": classes,
            "option_sets": {reference: options for reference, options in groups.items() if reference in reachable},
            "descriptions": deepcopy(source["descriptions"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=DESTINATION)
    arguments = parser.parse_args()
    payload = prepare_catalog(json.loads(arguments.source.read_text(encoding="utf-8")))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON preserves shared groups without expanding the graph.
    arguments.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Prepared {len(payload['classes'])} classes and {len(payload['option_sets'])} shared option sets: {arguments.output}")


if __name__ == "__main__":
    main()
