$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

function Resolve-LauncherPython {
    $venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    throw "Python was not found. Install Python 3.12+ or create .venv in this project."
}

$python = Resolve-LauncherPython

# RapidOCR depends on opencv-python, but this app intentionally uses
# opencv-python-headless. Install RapidOCR without pulling the GUI OpenCV wheel.
& $python -m pip install onnxruntime tqdm pyclipper Shapely PyYAML Pillow six
& $python -m pip install rapidocr-onnxruntime --no-deps

@'
from rapidocr_onnxruntime import RapidOCR
import onnxruntime
import cv2

print("RapidOCR OK")
print(f"ONNX Runtime: {onnxruntime.__version__}")
print(f"OpenCV: {cv2.__version__}")
'@ | & $python -
