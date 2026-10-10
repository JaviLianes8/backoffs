import importlib.resources

import backoffs

# The public API. Add every exported name here as the library grows; this list is the
# contract and the test below fails if the module and this list disagree.
PUBLIC_API: list[str] = ["backoff"]


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(backoffs.__all__) == sorted(PUBLIC_API)


def test_every_exported_name_resolves() -> None:
    for name in backoffs.__all__:
        assert hasattr(backoffs, name)


def test_version_is_a_three_part_string() -> None:
    parts = backoffs.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("backoffs").joinpath("py.typed").is_file()
