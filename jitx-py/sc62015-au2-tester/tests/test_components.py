from inspect import signature

from src.components import Sc62015B02


def test_sc62015_body_cutout_is_optional_and_defaults_on() -> None:
    interposer_cpu = Sc62015B02()
    tester_cpu = Sc62015B02(include_body_cutout=False)

    assert signature(Sc62015B02).parameters["include_body_cutout"].default is True
    assert "include_body_cutout" not in repr(interposer_cpu)
    assert "'include_body_cutout': False" in repr(tester_cpu)
