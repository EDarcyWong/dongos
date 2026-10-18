$ErrorActionPreference = 'Stop'
python (Join-Path $PSScriptRoot 'coordinate.py') serve @args
