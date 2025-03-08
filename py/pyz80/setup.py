from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext_modules = [
    Pybind11Extension(
        "pyz80",
        ["pyz80.cc"],
        include_dirs=["z80"],
    ),
]

setup(
    name="pyz80",
    version="1.0",
    author="mblsha",
    author_email="mblsha@example.com",
    description="Python wrapper for the SUZUKI PLAN Z80 Emulator",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
