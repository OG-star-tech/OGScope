"""
调试预设 API 的最小回归测试。
"""
import pytest


def _sample_preset(name: str = "night-sky") -> dict:
    return {
        "name": name,
        "description": "test preset",
        "exposure_us": 20000,
        "analogue_gain": 2.0,
        "digital_gain": 1.0,
        "auto_exposure": False,
        "auto_gain": False,
        "contrast": 1.0,
        "brightness": 0.0,
        "saturation": 1.0,
        "sharpness": 1.0,
        "noise_reduction": 0,
        "white_balance_mode": "auto",
        "white_balance_gain_r": 1.0,
        "white_balance_gain_b": 1.0,
        "rotation": 180,
        "color_mode": "color",
    }


@pytest.mark.unit
def test_debug_presets_empty(client, temp_debug_dir):
    response = client.get("/api/debug/camera/presets")
    assert response.status_code == 200
    assert response.json() == {"presets": []}


@pytest.mark.unit
def test_debug_presets_save_and_get(client, temp_debug_dir):
    payload = _sample_preset()
    save_resp = client.post("/api/debug/camera/presets", json=payload)
    assert save_resp.status_code == 200
    assert save_resp.json()["success"] is True

    get_resp = client.get("/api/debug/camera/presets")
    assert get_resp.status_code == 200
    presets = get_resp.json()["presets"]
    assert len(presets) == 1
    assert presets[0]["name"] == payload["name"]


@pytest.mark.unit
def test_debug_presets_update_same_name(client, temp_debug_dir):
    first = _sample_preset("deep-sky")
    second = _sample_preset("deep-sky")
    second["exposure_us"] = 30000

    assert client.post("/api/debug/camera/presets", json=first).status_code == 200
    assert client.post("/api/debug/camera/presets", json=second).status_code == 200

    get_resp = client.get("/api/debug/camera/presets")
    presets = get_resp.json()["presets"]
    assert len(presets) == 1
    assert presets[0]["exposure_us"] == 30000


@pytest.mark.unit
def test_debug_presets_delete(client, temp_debug_dir):
    payload = _sample_preset("to-delete")
    assert client.post("/api/debug/camera/presets", json=payload).status_code == 200

    delete_resp = client.delete("/api/debug/camera/presets/to-delete")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    get_resp = client.get("/api/debug/camera/presets")
    assert get_resp.status_code == 200
    assert get_resp.json()["presets"] == []

