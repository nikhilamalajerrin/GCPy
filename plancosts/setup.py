# setup.py
from setuptools import find_packages, setup

setup(
    name="gcpy-plancosts",  # <— match pyproject
    version="0.1.0",
    packages=find_packages(include=["plancosts", "plancosts.*"]),
    include_package_data=True,
    package_data={"plancosts": ["tests/*.json", "*.json"]},
    install_requires=["click", "requests"],
    entry_points={
        "console_scripts": [
            "plancosts=plancosts.main:main",   # <-- fix this line
        ]
    },

)
