"""
Quick import health check — run this before starting the server.

Usage (from project root):
    python check_imports.py

If everything is wired correctly you'll see a list of registered routes.
Any ImportError or missing module will be printed here instead of
crashing the server mid-startup.
"""
import sys
sys.path.insert(0, ".")

try:
    import importlib
    app_mod = importlib.import_module("404whisper.main")
    print("✓ App loaded:", app_mod.app.title)
    print("\nRegistered routes:")
    for route in app_mod.app.routes:
        if hasattr(route, "methods"):
            methods = ", ".join(sorted(route.methods))
            print(f"  [{methods}]  {route.path}")
    print("\n✓ All imports OK — safe to run the server.")
except Exception as exc:
    print(f"\n✗ Import failed: {exc}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
