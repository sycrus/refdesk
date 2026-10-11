import sys
from pathlib import Path

# Make scripts/ importable so the build-loop verifier can be unit-tested.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
