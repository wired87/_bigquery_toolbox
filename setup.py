from setuptools import setup, find_packages

setup(
    name="bq-toolbox-cli",
    version="1.0.0",
    packages=find_packages(include=["toolbox_cli", "toolbox_cli.*"]),
    install_requires=[
        "typer",
        "rich",
        "httpx",
        "websockets",
        "SpeechRecognition",
        "pyttsx3",
        "ray" # Optional but listed
    ],
    entry_points={
        "console_scripts": [
            "bq-toolbox=toolbox_cli.main:app",
        ],
    },
)
