import json
import importlib.util
from pathlib import Path


SPEC_PATH = Path(__file__).resolve().parents[1] / "nginx/home/proxyuser/run_add_project_address.py"
spec = importlib.util.spec_from_file_location("run_add_project_address", SPEC_PATH)
run_add = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_add)


def test_load_json_reads_data(tmp_path: Path):
    data = {"proj": ["1.2.3.4"]}
    file_path = tmp_path / "mapping.json"
    file_path.write_text(json.dumps(data))
    assert run_add.load_json(str(file_path)) == data


def test_save_json_writes_compact(tmp_path: Path):
    data = {"key": "value"}
    file_path = tmp_path / "out.json"
    assert run_add.save_json(str(file_path), data)
    assert file_path.read_text() == '{"key":"value"}'
    assert json.loads(file_path.read_text()) == data
