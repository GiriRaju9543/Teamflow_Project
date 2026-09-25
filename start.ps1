$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" manage.py migrate
& "$PSScriptRoot\.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000 --noreload
