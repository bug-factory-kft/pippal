from __future__ import annotations

import json

import pytest
from pippal_e2e import (
    apply_settings,
    assert_actionable_controls_accounted_for,
    assert_audio_chunk_ready,
    assert_backend_class,
    assert_controls_cover,
    assert_port_free,
    assert_window_texts_contain,
    find_control,
    get_runtime_state,
    launch_public_app,
    open_settings_window,
    open_voice_manager_via_command,
    post_empty,
    post_json,
    run_source_open_file_helper,
    terminate_process_tree,
    ui_click,
    ui_overlay_click,
    ui_select,
    ui_set,
    ui_type,
    wait_for_audio_chunk,
    wait_for_port_or_process_exit,
    wait_for_state,
)

SETTINGS_VARIABLES = [
    "engine",
    "voice_display",
    "speed",
    "noise_scale",
    "hotkey_speak",
    "hotkey_queue",
    "hotkey_pause",
    "hotkey_stop",
    "show_overlay",
    "show_text_in_overlay",
    "auto_hide_ms",
    "overlay_y_offset",
    "karaoke_offset_ms",
]

SETTINGS_BUTTONS = [
    "✕",
    "Manage…",
    "Install",
    "Remove",
    "Reset to defaults",
    "Save",
    "Apply",
    "Cancel",
]

SETTINGS_LABELS = [
    "Engine",
    "Voice",
    "Speed",
    "Variation",
    "Read selection",
    "Queue selection",
    "Pause / Resume",
    "Stop",
    "Auto-hide delay",
    "Distance from taskbar",
    "Karaoke offset",
]


@pytest.mark.live_ui
@pytest.mark.public
def test_public_source_install_opens_settings(public_root, data_root) -> None:
    assert_port_free()
    process = launch_public_app(public_root, data_root)
    try:
        wait_for_port_or_process_exit(process)
        state = open_settings_window()
        assert_window_texts_contain(
            state,
            [
                "Settings",
                "Voice",
                "Speech",
                "Hotkeys",
                "Reader panel",
                "Windows integration",
                "About",
                "Save",
            ],
        )
    finally:
        terminate_process_tree(process)


@pytest.mark.live_ui
@pytest.mark.public
def test_public_runtime_registry_is_core_only(running_public_app) -> None:
    open_settings_window()
    state = get_runtime_state()

    assert state["engines"] == ["piper"]
    assert state["plugin_actions"] == []
    assert state["hotkey_actions"] == ["speak", "queue", "pause", "stop"]
    assert all(".ui.ai_" not in item for item in state["settings_cards"])
    assert all(".ui.mood_" not in item for item in state["tray_items"])


@pytest.mark.live_ui
@pytest.mark.public
def test_public_settings_apply_persists_core_values(running_public_app, data_root) -> None:
    open_settings_window()

    state = apply_settings(
        {
            "engine": "piper",
            "show_overlay": False,
            "show_text_in_overlay": False,
            "speed": 1.25,
            "noise_scale": 0.55,
            "auto_hide_ms": 2400,
            "overlay_y_offset": 150,
            "karaoke_offset_ms": -60,
        },
    )

    config = state["config"]
    assert config["engine"] == "piper"
    assert config["show_overlay"] is False
    assert config["show_text_in_overlay"] is False
    assert config["length_scale"] == 0.8
    assert config["noise_scale"] == 0.55
    assert config["auto_hide_ms"] == 2400
    assert config["overlay_y_offset"] == 150
    assert config["karaoke_offset_ms"] == -60

    saved = json.loads((data_root / "config.json").read_text(encoding="utf-8"))
    assert saved["show_overlay"] is False
    assert saved["auto_hide_ms"] == 2400


@pytest.mark.live_ui
@pytest.mark.public
def test_public_settings_controls_are_accounted_for_and_editable(
    running_public_app,
    data_root,
) -> None:
    state = open_settings_window()
    assert_controls_cover(
        state,
        variables=SETTINGS_VARIABLES,
        buttons=SETTINGS_BUTTONS,
        labels=SETTINGS_LABELS,
        title="PipPal",
    )
    assert_actionable_controls_accounted_for(
        state,
        title="PipPal",
        variables=SETTINGS_VARIABLES,
        buttons=SETTINGS_BUTTONS,
        labels=SETTINGS_LABELS,
    )

    for key, value in {
        "hotkey_speak": "windows+shift+r",
        "hotkey_queue": "windows+shift+q",
        "hotkey_pause": "windows+shift+p",
        "hotkey_stop": "windows+shift+b",
        "auto_hide_ms": "3100",
        "overlay_y_offset": "170",
        "karaoke_offset_ms": "-40",
    }.items():
        state = ui_type({"var_key": key}, value)
        assert str(state["settings_vars"][key]) == value

    ui_set("speed", 1.33)
    ui_set("noise_scale", 0.61)
    ui_set("show_overlay", False)
    ui_set("show_text_in_overlay", False)
    state = ui_click({"text": "Apply"})

    config = state["config"]
    assert config["length_scale"] == 0.752
    assert config["noise_scale"] == 0.61
    assert config["show_overlay"] is False
    assert config["show_text_in_overlay"] is False
    assert config["auto_hide_ms"] == 3100
    assert config["overlay_y_offset"] == 170
    assert config["karaoke_offset_ms"] == -40

    saved = (data_root / "config.json").read_text(encoding="utf-8")
    assert '"auto_hide_ms": 3100' in saved
    assert '"karaoke_offset_ms": -40' in saved


@pytest.mark.live_ui
@pytest.mark.public
def test_public_settings_buttons_and_links_fire(running_public_app) -> None:
    open_settings_window()
    state = ui_click({"text": "Manage…"})
    assert any(window.get("title") == "Voices" for window in state["windows"])
    state = ui_click({"title": "Voices", "text": "✕"})
    assert all(window.get("title") != "Voices" for window in state["windows"])

    state = ui_click({"text": "Website", "role": ""})
    assert state["opened_urls"] == ["https://pippal.bugfactory.hu"]
    state = ui_click({"text": "GitHub", "role": ""})
    assert state["opened_urls"] == ["https://github.com/bug-factory-kft/pippal"]
    state = ui_click({"text": "Privacy", "role": ""})
    assert state["opened_urls"] == [
        "https://github.com/bug-factory-kft/pippal/blob/main/docs/PRIVACY.md"
    ]
    state = ui_click({"text": "Terms", "role": ""})
    assert state["opened_urls"] == [
        "https://github.com/bug-factory-kft/pippal/blob/main/docs/TERMS.md"
    ]

    ui_click({"text": "Install"})
    ui_click({"text": "Remove"})

    ui_set("show_overlay", True)
    ui_click({"text": "Apply"})
    ui_set("show_overlay", False)
    state = ui_click({"text": "Cancel"})
    assert state["settings_open"] is False
    assert get_runtime_state()["config"]["show_overlay"] is True

    open_settings_window()
    ui_set("show_overlay", False)
    state = ui_click({"text": "Save"})
    assert state["settings_open"] is False
    assert state["config"]["show_overlay"] is False

    open_settings_window()
    ui_set("show_overlay", True)
    ui_set("speed", 1.42)
    ui_click({"text": "Reset to defaults"}, confirm=True)
    state = ui_click({"text": "Apply"})
    assert state["settings_open"] is True
    assert state["config"]["show_overlay"] is True
    assert state["config"]["length_scale"] == 1.0

    state = ui_click({"text": "✕", "title": "PipPal"})
    assert state["settings_open"] is False


@pytest.mark.live_ui
@pytest.mark.public
def test_public_voice_manager_controls_are_accounted_for_and_editable(
    running_public_app,
) -> None:
    open_settings_window()
    open_voice_manager_via_command()
    state = wait_for_state(
        lambda current: "Voices" in current["settings_texts"],
        description="Voice Manager window",
    )
    assert_controls_cover(
        state,
        buttons=["✕", "Close"],
        labels=["Language", "Quality", "Status", "Search"],
        title="Voices",
    )
    assert_actionable_controls_accounted_for(
        state,
        title="Voices",
        variables=[],
        buttons=["✕", "Install", "Remove", "Close"],
        labels=["Language", "Quality", "Status", "Search"],
    )
    assert any(
        control.get("role") == "button"
        and control.get("text") in {"Install", "Remove"}
        for control in state["controls"]
    )

    lang_values = find_control(state, label="Language", role="select").get("values", [])
    if "English (US)" in lang_values:
        ui_select({"title": "Voices", "label": "Language"}, "English (US)")

    state = ui_select({"title": "Voices", "label": "Quality"}, "high")
    assert find_control(state, label="Quality", role="select")["value"] == "high"

    state = ui_select({"title": "Voices", "label": "Status"}, "Installed")
    assert find_control(state, label="Status", role="select")["value"] == "Installed"

    ui_type({"title": "Voices", "label": "Search"}, "ryan")
    state = wait_for_state(
        lambda current: any("Ryan" in str(text) for text in current["settings_texts"]),
        description="Voice Manager search result",
    )
    assert find_control(state, label="Search", role="input")["value"] == "ryan"

    state = ui_click({"title": "Voices", "text": "Remove"}, confirm=False)
    assert any(window.get("title") == "Voices" for window in state["windows"])

    state = ui_click({"title": "Voices", "text": "Close"})
    assert all(window.get("title") != "Voices" for window in state["windows"])


@pytest.mark.live_ui
@pytest.mark.public
def test_public_piper_read_aloud_generates_playback_audio(running_public_app) -> None:
    state = apply_settings({"engine": "piper"})
    assert state["config"]["engine"] == "piper"

    before = int(get_runtime_state()["token"])
    try:
        post_json("/read", {"text": "Public live Piper read aloud verification."})
        state = wait_for_audio_chunk(backend_class="PiperBackend")

        assert int(state["token"]) > before
        assert_backend_class(state, "PiperBackend")
        assert state["config"]["engine"] == "piper"
        assert any("Public live Piper" in chunk for chunk in state["chunks"])
        assert state["history"][0] == "Public live Piper read aloud verification."
        assert_audio_chunk_ready(state)
    finally:
        post_empty("/stop")


@pytest.mark.live_ui
@pytest.mark.public
def test_public_reader_panel_buttons_route_to_live_engine(running_public_app) -> None:
    state = apply_settings({"engine": "piper", "show_overlay": True})
    assert state["config"]["show_overlay"] is True

    text = (
        "Reader panel control verification keeps audio active and gives "
        "the playback session enough words for previous replay next and close "
        "controls to run against multiple generated chunks "
    ) * 10
    try:
        post_json("/read", {"text": text})
        state = wait_for_audio_chunk(backend_class="PiperBackend")
        assert len(state["chunks"]) >= 3
        wait_for_state(
            lambda current: {"prev", "replay", "next"} <= set(current["overlay_buttons"]),
            description="reader panel button rectangles",
        )

        post_empty("/pause")
        state = wait_for_state(
            lambda current: current["is_paused"] is True,
            description="pause command",
        )
        assert state["is_speaking"] is True

        post_empty("/pause")
        wait_for_state(
            lambda current: current["is_paused"] is False and current["is_speaking"],
            description="resume command",
        )

        ui_overlay_click("next")
        wait_for_state(
            lambda current: int(current.get("chunk_idx", 0)) >= 1,
            description="reader panel next button",
        )
        ui_overlay_click("replay")
        ui_overlay_click("prev")
        state = ui_overlay_click("close")
        assert state["is_speaking"] is False
    finally:
        post_empty("/stop")


@pytest.mark.live_ui
@pytest.mark.public
def test_public_command_server_validates_payloads_and_open_file_helper(
    running_public_app,
    public_root,
    tmp_path,
) -> None:
    assert post_json("/read", {"text": ""}, expected_status=400) is not None
    assert post_json("/read", {"text": "x" * (220 * 1024)}, expected_status=413) is not None
    assert post_json("/read-file", {"path": str(tmp_path / "missing.txt")},
                     expected_status=404) is not None

    expected = "Public command helper text."
    readable = tmp_path / "read-me.txt"
    readable.write_text(expected, encoding="utf-8")

    before = int(get_runtime_state()["token"])
    run_source_open_file_helper(public_root, readable)
    state = wait_for_state(
        lambda current: (
            int(current["token"]) > before
            and current["history"]
            and current["history"][0] == expected
        ),
        description="source open_file dispatch records Recent history",
    )
    assert state["history"][0] == expected
    post_empty("/stop")
