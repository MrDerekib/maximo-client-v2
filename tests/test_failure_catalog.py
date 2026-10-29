from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import failure_catalog as catalog
from tools.prepare_failure_catalog import SOURCE, prepare_catalog


class FailureCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))

    def selection(self, class_code, *codes):
        selection = {"class_key": "TRANSPORTES|" + class_code, "option_keys": []}
        for code in codes:
            options = [item for item in catalog.choices(**selection) if item["code"] == code]
            self.assertEqual(len(options), 1, (class_code, code, options))
            selection["option_keys"].append(options[0]["key"])
        return selection

    def test_default_is_complete_and_described(self):
        selected = catalog.default_selection()
        resolved = catalog.resolve_selection(selected)
        self.assertEqual(resolved["class_key"], "TRANSPORTES|RFN-70")
        self.assertEqual(resolved["class_code"], "RFN-70")
        self.assertEqual(resolved["organization"], "TRANSPORTES")
        self.assertEqual([(item["type"], item["code"]) for item in resolved["path"]],
                         [("PROBLEM", "OTROS-01"), ("CAUSE", "OTROS-02"), ("REMEDY", "OTROS-03")])
        self.assertTrue(all(item["description"] for item in resolved["path"]))
        self.assertTrue(all(isinstance(item["allow_duplicate"], bool) for item in resolved["path"]))
        self.assertEqual(catalog.choices(**selected), [])

    def test_problem_and_cause_terminal_paths_are_complete(self):
        for class_code, codes, expected_types in (
                ("LG-01", ("LG-01-01",), ["PROBLEM"]),
                ("FGV-20", ("P-0170", "C-0370"), ["PROBLEM", "CAUSE"])):
            with self.subTest(class_code=class_code):
                selected = self.selection(class_code, *codes)
                self.assertEqual(catalog.choices(**selected), [])
                self.assertEqual([item["type"] for item in catalog.resolve_selection(selected)["path"]], expected_types)

    def test_class_can_start_directly_at_cause(self):
        selected = self.selection("CD-19", "CD-19-0-3")
        with self.assertRaisesRegex(ValueError, "incompleta"):
            catalog.resolve_selection(selected)
        remedies = catalog.choices(**selected)
        self.assertEqual({(item["code"], item["type"]) for item in remedies},
                         {(f"CD-19-0-3-{index}", "REMEDY") for index in range(1, 5)})
        selected["option_keys"].append(remedies[0]["key"])
        self.assertEqual([item["type"] for item in catalog.resolve_selection(selected)["path"]], ["CAUSE", "REMEDY"])

    def test_incomplete_stale_foreign_and_overlong_paths_fail(self):
        default = catalog.default_selection()
        invalid = [
            {"class_key": default["class_key"], "option_keys": []},
            {**default, "option_keys": default["option_keys"][:-1]},
            {**default, "class_key": "UNKNOWN|RFN-70"},
            {**default, "option_keys": ["outdated:0"]},
            {**default, "option_keys": [*default["option_keys"], default["option_keys"][-1]]},
            {**default, "class_key": "TRANSPORTES|LG-01"},
            {**default, "option_keys": "bad"},
            {**default, "option_keys": [None]},
            {}, None,
        ]
        for selected in invalid:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                catalog.resolve_selection(selected)

    def test_changing_parent_invalidates_previous_child(self):
        selected = self.selection("RFN-20", "P-RFN-139", "C-RFN-062", "S-RFN-262")
        other_parent = next(item for item in catalog.choices(selected["class_key"])
                            if item["code"] != "P-RFN-139" and
                            not any(child["key"] == selected["option_keys"][1]
                                    for child in catalog.choices(selected["class_key"], [item["key"]])))
        selected["option_keys"][0] = other_parent["key"]
        with self.assertRaisesRegex(ValueError, "padre"):
            catalog.choices(**selected)
        with self.assertRaisesRegex(ValueError, "padre"):
            catalog.resolve_selection(selected)

    def test_confirmed_duplicate_cause_has_only_confirmed_successor(self):
        prefix = self.selection("RFN-20", "P-RFN-139")
        causes = [item for item in catalog.choices(**prefix) if item["code"] == "C-RFN-062"]
        self.assertEqual(len(causes), 1)
        self.assertTrue(causes[0]["allow_duplicate"])
        # Keep original occurrence index 3 even after dropping occurrence 2.
        self.assertTrue(causes[0]["key"].endswith(":3"))
        selected = self.selection("RFN-20", "P-RFN-139", "C-RFN-062", "S-RFN-262")
        self.assertEqual([item["code"] for item in catalog.choices(prefix["class_key"], selected["option_keys"][:2])],
                         ["S-RFN-262"])
        self.assertTrue(catalog.resolve_selection(selected)["path"][1]["allow_duplicate"])

    def test_equivalent_leaf_duplicates_group_with_explicit_permission(self):
        payload = catalog.catalog_payload()
        original = self.source["option_sets"]["g_81eaeb13071fcbdd"]
        self.assertEqual(len(original), 2)
        prepared = payload["option_sets"]["g_81eaeb13071fcbdd"]
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0]["code"], "R-0370")
        self.assertEqual(prepared[0]["key"], "g_81eaeb13071fcbdd:0")
        self.assertTrue(prepared[0]["allow_duplicate"])

    def test_leaf_occurrences_with_different_data_are_not_collapsed(self):
        source = deepcopy(self.source)
        source["option_sets"]["different_leaves"] = [
            {"code": "R-SAME", "type": "REMEDY", "provenance": "first"},
            {"code": "R-SAME", "type": "REMEDY", "provenance": "second"},
        ]
        source["classes"].append({"organization": "OTHER", "code": "DIFFERENT", "description": "",
                                  "options_ref": "different_leaves"})
        payload = prepare_catalog(source)
        self.assertEqual(len(payload["option_sets"]["different_leaves"]), 2)
        with patch.object(catalog, "_catalog", return_value=payload):
            with self.assertRaisesRegex(ValueError, "no equivalentes"):
                catalog.resolve_selection({"class_key": "OTHER|DIFFERENT", "option_keys": ["different_leaves:0"]})

    def test_descriptions_are_resolved_for_class_organization(self):
        payload = catalog.catalog_payload()
        original = next(item for item in payload["classes"] if item["key"] == "TRANSPORTES|LG-01")
        payload["classes"].append({**original, "key": "OTHER|LG-01", "organization": "OTHER"})
        payload["descriptions"]["OTHER"] = {"LG-01-01": "Descripción de otra organización"}
        with patch.object(catalog, "_catalog", return_value=payload):
            option = next(item for item in catalog.choices("OTHER|LG-01") if item["code"] == "LG-01-01")
            self.assertEqual(option["description"], "Descripción de otra organización")
            resolved = catalog.resolve_selection({"class_key": "OTHER|LG-01", "option_keys": [option["key"]]})
            self.assertEqual(resolved["path"][0]["description"], option["description"])

    def test_exclusion_does_not_mutate_source_or_shared_contexts(self):
        source = deepcopy(self.source)
        before = deepcopy(source)
        original_class = next(item for item in source["classes"] if item["code"] == "RFN-20")
        source["classes"].append({**original_class, "organization": "OTHER"})
        payload = prepare_catalog(source)
        self.assertEqual(source["option_sets"], before["option_sets"])
        classes = {item["key"]: item for item in payload["classes"]}
        self.assertNotEqual(classes["OTHER|RFN-20"]["options_ref"], classes["TRANSPORTES|RFN-20"]["options_ref"])
        groups = payload["option_sets"]
        other_root = groups[classes["OTHER|RFN-20"]["options_ref"]]
        other_problem = next(item for item in other_root if item["code"] == "P-RFN-139")
        other_causes = [item for item in groups[other_problem["children_ref"]] if item["code"] == "C-RFN-062"]
        self.assertEqual(len(other_causes), 2)
        self.assertEqual({child["code"] for item in other_causes for child in groups[item["children_ref"]]},
                         {"S-RFN-262", "S-RFN-263"})
        # Non-equivalent occurrences remain uniquely keyed and fail explicitly.
        self.assertNotEqual(other_causes[0]["key"], other_causes[1]["key"])
        with patch.object(catalog, "_catalog", return_value=payload):
            with self.assertRaisesRegex(ValueError, "no equivalentes"):
                catalog.resolve_selection({"class_key": "OTHER|RFN-20", "option_keys":
                                           [other_problem["key"], other_causes[0]["key"]]})

    def test_resource_is_reproducible_compact_and_independent(self):
        resource = catalog._resource_path()
        payload = catalog.catalog_payload()
        self.assertEqual(payload, prepare_catalog(self.source))
        self.assertLess(resource.stat().st_size, 3_000_000)
        self.assertLess(len(payload["option_sets"]), 1700)
        self.assertEqual(len(payload["classes"]), 126)
        self.assertEqual(set(payload), {"version", "classes", "option_sets", "descriptions"})
        # Caller edits must not corrupt the cached catalogue or default path.
        payload["classes"].clear()
        self.assertEqual(len(catalog.catalog_payload()["classes"]), 126)
        json.dumps(catalog.resolve_selection(catalog.default_selection()))

    def test_portable_resource_loads_without_docs_or_source_checkout(self):
        temporary = Path(tempfile.gettempdir()) / ("failure-catalog-portable-" + uuid4().hex)
        temporary.mkdir()
        self.addCleanup(shutil.rmtree, temporary)
        (temporary / "resources").mkdir()
        shutil.copy2(catalog.__file__, temporary / "failure_catalog.py")
        shutil.copy2(catalog._resource_path(), temporary / "resources/failure_catalog.json")
        (temporary / "app_paths.py").write_text("from pathlib import Path\nPROGRAM_DIR = Path(__file__).resolve().parent\n", encoding="utf-8")
        command = [sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); import failure_catalog as c; "
                   "assert c.resolve_selection(c.default_selection())['class_code'] == 'RFN-70'; "
                   "assert len(c.catalog_payload()['classes']) == 126", str(temporary)]
        completed = subprocess.run(command, cwd=temporary, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
