## Compiling to an App

>[!WARNING]
> This is a very experimental feature, and is not guaranteed to work on all systems. If you have any issues, please open an issue on the GitHub repo.

PyInstaller is used to build the app to a single file or a standalone executable. It is still in development, so it is not recommended for use.

```bash
git clone https://github.com/noblecloud/LevityDash.git
cd LevityDash
poetry install
cd build
poetry run python build.py
```