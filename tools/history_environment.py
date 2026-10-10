"""Read-only probe of available acceptance tools."""
import importlib.util
import sys
print('Python:', sys.version)
print('Modules:', {n: bool(importlib.util.find_spec(n)) for n in ('playwright', 'webview', 'websocket', 'requests', 'gi')})
