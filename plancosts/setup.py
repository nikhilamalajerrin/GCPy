from setuptools import setup, find_packages

setup(
    name="plancosts",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click",
        "requests",
    ],
    entry_points={
        'console_scripts': [
            'plancosts=main:main',
        ],
    },
)