# Installation Guide

This project supports local development on both **Windows PCs** and **Raspberry Pi** devices.

> [!IMPORTANT]
> The repository uses the **fuzzy enigma card recognizer** as a git submodule at `third_party/fuzzy-enigma-card-recognition`. Always initialize and update submodules after cloning.
>
> `pip install -e .[dev]` in this repository installs this project's dependencies, but it does **not automatically install all fuzzy-enigma OCR runtime dependencies** (such as RapidOCR bindings). Install the submodule dependencies in the steps below.

## 1) Common prerequisites

- Git (2.34+ recommended)
- Python 3.11+
- `pip` (latest available for your Python)

Optional but recommended:

- A virtual environment tool (`venv` is built into Python)

---

## 2) Windows PC installation

These steps use **PowerShell**.

### Step A — Clone with submodules

```powershell
git clone --recurse-submodules https://github.com/<your-org-or-user>/SortingMachineArray.git
cd SortingMachineArray
```

If you already cloned without submodules:

```powershell
git submodule update --init --recursive
```

### Step B — Create and activate a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step C — Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -e .[dev]
```

If you plan to connect real hardware from Windows, install hardware extras too:

```powershell
pip install -e .[dev,hardware]
```

### Step C.1 — Install fuzzy enigma + RapidOCR dependencies

```powershell
pip install -e .\third_party\fuzzy-enigma-card-recognition
pip install rapidocr-onnxruntime
```

If the submodule ships a requirements file in your checked-out version, install it too:

```powershell
pip install -r .\third_party\fuzzy-enigma-card-recognition\requirements.txt
```

### Step D — Verify the fuzzy enigma submodule is present

```powershell
Test-Path .\third_party\fuzzy-enigma-card-recognition\src
```

Expected output: `True`

### Step E — Quick validation

```powershell
pytest -q
python -c "import rapidocr_onnxruntime; print('rapidocr ok')"
python -m sorter.interfaces.cli --mode sim
```

---

## 3) Raspberry Pi installation

These steps assume Raspberry Pi OS (Bookworm/Bullseye) and shell access.

### Step A — Install system packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

If your Pi image does not already provide Python 3.11, install the newest Python available for your distro and use that version in the venv commands below.

### Step B — Clone with submodules

```bash
git clone --recurse-submodules https://github.com/<your-org-or-user>/SortingMachineArray.git
cd SortingMachineArray
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

### Step C — Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step D — Install dependencies

```bash
python -m pip install --upgrade pip
pip install -e .[dev,hardware]
```

### Step D.1 — Install fuzzy enigma + RapidOCR dependencies

```bash
pip install -e ./third_party/fuzzy-enigma-card-recognition
pip install rapidocr-onnxruntime
```

If the submodule ships a requirements file in your checked-out version, install it too:

```bash
pip install -r ./third_party/fuzzy-enigma-card-recognition/requirements.txt
```

### Step E — Verify the fuzzy enigma submodule is present

```bash
test -d third_party/fuzzy-enigma-card-recognition/src && echo "OK"
```

Expected output: `OK`

### Step F — Quick validation

```bash
pytest -q
python -c "import rapidocr_onnxruntime; print('rapidocr ok')"
python -m sorter.interfaces.cli --mode sim
```

For hardware wiring smoke checks on Raspberry Pi:

```bash
python scripts/hardware_smoke_test.py
```

---

## 4) Keeping the fuzzy enigma submodule updated

From the repository root:

```bash
git submodule sync --recursive
git submodule update --init --recursive --remote
```

Then commit the updated submodule pointer in this repository:

```bash
git add third_party/fuzzy-enigma-card-recognition
git commit -m "chore: bump fuzzy enigma recognizer submodule"
```

---

## 5) Troubleshooting

- **Submodule tests fail because recognizer package is missing**
  - Run: `git submodule update --init --recursive`
  - Confirm `third_party/fuzzy-enigma-card-recognition/src` exists.

- **`pip install -e .[dev]` fails on Raspberry Pi**
  - Upgrade pip first: `python -m pip install --upgrade pip`
  - Re-run install command inside an activated virtual environment.

- **PowerShell blocks virtualenv activation script**
  - Run PowerShell as your user and temporarily allow local scripts:
    - `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
