from setuptools import setup

setup(
    name="bq-toolbox-cli",
    version="1.0.0",
    py_modules=["cli", "remote_engine", "speech_handler", "ip_manager"],
    install_requires=[
        "typer",
        "rich",
        "httpx",
        "websockets",
        "SpeechRecognition",
        "pyttsx3"
    ],
    entry_points={
        "console_scripts": [
            "bq-toolbox=cli:main",
        ],
    },
)
