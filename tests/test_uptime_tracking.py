import json
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "gen_ports", Path(__file__).resolve().parents[1] / "nginx/generate_ports_json.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def test_uptime_increments_and_resets(tmp_path, monkeypatch):
    ip_map = tmp_path / "ip_mapping.json"
    port_map = tmp_path / "port_mapping.json"
    uptime_file = tmp_path / "uptime.json"
    out_file = tmp_path / "ports.json"

    ip_map.write_text(json.dumps({"proj": ["1.2.3.4"]}))
    port_map.write_text(json.dumps({"proj": [1234]}))
    uptime_file.write_text("{}")

    monkeypatch.setattr(gen, "IP_MAPPING_FILE", str(ip_map))
    monkeypatch.setattr(gen, "PORT_MAPPING_FILE", str(port_map))
    monkeypatch.setattr(gen, "UPTIME_FILE", str(uptime_file))
    monkeypatch.setattr(gen, "OUTPUT_FILE", str(out_file))
    monkeypatch.setattr(gen, "lookup_country", lambda ip: "US")

    t0 = datetime(2025, 1, 1, 0, 0, 0)
    gen.main(now=t0)
    data = json.loads(out_file.read_text())
    assert data["projects"][0]["ports"][0]["uptime"] == "0d 00:00:00"

    t1 = t0 + timedelta(minutes=2)
    gen.main(now=t1)
    data = json.loads(out_file.read_text())
    assert data["projects"][0]["ports"][0]["uptime"] == "0d 00:02:00"

    ip_map.write_text(json.dumps({"proj": []}))
    t2 = t1 + timedelta(seconds=5)
    gen.main(now=t2)
    data = json.loads(out_file.read_text())
    assert data["projects"][0]["ports"][0]["status"] == "inactive"
    assert data["projects"][0]["ports"][0]["uptime"] == "—"
    assert json.loads(uptime_file.read_text()) == {}

