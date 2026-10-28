"""Pinned WeChat build using the shared verifier. Never install or run source."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('social_vendor_builder',ROOT.parent/'build/fetch-and-patch.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.ROOT=ROOT

if __name__=='__main__':
    raise SystemExit(builder.main())
