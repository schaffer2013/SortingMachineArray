param(
    [switch]$WithHardware,
    [switch]$SkipTests,
    [switch]$SkipSimRun
)

$ErrorActionPreference = 'Stop'

Write-Host '==> Ensuring submodules are initialized'
git submodule update --init --recursive

Write-Host '==> Creating virtual environment (.venv)'
if (-not (Test-Path '.venv')) {
    py -3.11 -m venv .venv
}

Write-Host '==> Activating virtual environment'
. .\.venv\Scripts\Activate.ps1

Write-Host '==> Upgrading pip'
python -m pip install --upgrade pip

Write-Host '==> Installing project dependencies'
if ($WithHardware) {
    pip install -e '.[dev,hardware]'
} else {
    pip install -e '.[dev]'
}

Write-Host '==> Installing fuzzy-enigma recognizer and OCR runtime'
pip install -e .\third_party\fuzzy-enigma-card-recognition
pip install rapidocr-onnxruntime

if (Test-Path '.\third_party\fuzzy-enigma-card-recognition\requirements.txt') {
    Write-Host '==> Installing submodule requirements.txt'
    pip install -r .\third_party\fuzzy-enigma-card-recognition\requirements.txt
}

Write-Host '==> Verifying submodule path and RapidOCR import'
if (-not (Test-Path '.\third_party\fuzzy-enigma-card-recognition\src')) {
    throw 'Submodule source path missing: .\third_party\fuzzy-enigma-card-recognition\src'
}
python -c "import rapidocr_onnxruntime; print('rapidocr ok')"

if (-not $SkipTests) {
    Write-Host '==> Running test suite'
    pytest -q
}

if (-not $SkipSimRun) {
    Write-Host '==> Running sim CLI smoke check'
    python -m sorter.interfaces.cli --mode sim
}

Write-Host 'Installation complete.'
