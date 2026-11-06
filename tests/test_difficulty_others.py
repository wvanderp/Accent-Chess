"""Native difficulty readback regressions, independent of installed emulators."""
from pathlib import Path

import pytest
from PIL import Image

from games.Chess_19xx import difficulty as c64
from games.Battle_Chess import difficulty as st


def test_all_c64_strength_digits() -> None:
    with Image.open(Path(c64.__file__).with_name("difficulty-levels.png")) as strip:
        for index, (profile, _) in enumerate(c64.PROFILES):
            frame = Image.new("RGB", (640, 480), (0, 0, 0))
            with Image.open(Path(c64.__file__).with_name("difficulty-label.png")) as label:
                frame.paste(label, (425, 216))
            frame.paste(strip.crop((13*index, 0, 13*index+13, 9)), c64.BOX[:2])
            assert c64.read_difficulty(frame) == profile


def test_c64_blank_strength_rejected() -> None:
    with pytest.raises(ValueError):
        c64.read_difficulty(Image.new("RGB", (640, 480)))


def test_st_all_selected_rows() -> None:
    with Image.open(Path(st.__file__).with_name("difficulty-level-menu.png")) as source:
        image = source.convert("RGB")
    # The captured menu has Level 2 selected. Preserve the real marker glyph.
    marker = image.crop((425, 169, 439, 181))
    image.paste((34, 34, 136), (425, 130, 439, 300))
    for index, (profile, _) in enumerate(st.PROFILES):
        frame = image.copy()
        frame.paste(marker, (425, 137+16*index))
        assert st.read_difficulty(frame) == profile


def test_st_blank_menu_rejected() -> None:
    with pytest.raises(ValueError):
        st.read_difficulty(Image.new("RGB", (640, 480)))


def test_st_unfolding_menu_rejected() -> None:
    with Image.open(Path(st.__file__).with_name("difficulty-level-menu.png")) as source:
        image = source.convert("RGB")
    image.paste((0, 0, 0), (420, 296, 580, 315))
    with pytest.raises(ValueError, match="unfolding"):
        st.read_difficulty(image)
    assert st.hovered_level(image) is None


@pytest.mark.parametrize("module", [c64, st])
def test_invalid_profile_rejected_before_input(module: object) -> None:
    with pytest.raises(ValueError):
        module.set_difficulty(None, "level-0")  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        module.set_difficulty(None, "level-10")  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        module.set_difficulty(None, "level-1", timeout=0)  # type: ignore[attr-defined]
