
@REM check if windows10-venv exists

if [ ! -d "windows10-venv" ]; then
		# create virtual environment
		python3 -m venv windows10-venv
fi

@REM activate virtual environment
windows10-venv/bin/activate

@REM install requirements
python -m pip install --extra-index-url https://repo.levityda.sh/ "levitydash[build]"
