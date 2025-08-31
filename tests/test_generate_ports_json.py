import json
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "generate_ports_json", Path(__file__).resolve().parents[1] / "generate_ports_json.py"
)
gpj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpj)


def test_merge_ports_and_filter_empty():
    occupied = {"proj1": [1, 2], "proj2": []}
    available = {"proj1": [3], "proj3": [4]}
    result = gpj.merge_ports(occupied, available)
    assert result == {
        "proj1": {"occupied_ports": [1, 2], "available_ports": [3]},
        "proj3": {"occupied_ports": [], "available_ports": [4]},
    }


def test_generate_ports_json_reads_and_writes(tmp_path: Path):
    occupied_file = tmp_path / "occ.json"
    available_file = tmp_path / "avail.json"
    out_file = tmp_path / "out.json"
    json.dump({"p": [1]}, occupied_file.open("w"))
    json.dump({"p": [2]}, available_file.open("w"))

    merged = gpj.generate_ports_json(str(occupied_file), str(available_file), str(out_file))
    assert merged == {"p": {"occupied_ports": [1], "available_ports": [2]}}
    assert json.loads(out_file.read_text()) == merged
