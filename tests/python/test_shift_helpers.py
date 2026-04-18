import generate_schedule as gs


def test_make_shift_returns_expected_dict():
    assert gs.make_shift("5:00", "13:00", 8) == {"start": "5:00", "end": "13:00", "hrs": 8}


def test_off_has_zero_hours():
    shift = gs.off()
    assert shift["hrs"] == 0
    assert shift["start"] == "Off"
    assert shift["end"] == "Off"


def test_cleet_has_zero_hours():
    shift = gs.cleet()
    assert shift["hrs"] == 0
    assert shift["start"] == "CLEET"


def test_ro_has_zero_hours():
    shift = gs.ro()
    assert shift["hrs"] == 0
    assert shift["start"] == "R/O"


def test_s8_constants_are_eight_hours():
    for ctor in (gs.S8_13_21, gs.S8_21_5, gs.S8_5_13, gs.S8_3_11, gs.S8_11_19):
        assert ctor()["hrs"] == 8
