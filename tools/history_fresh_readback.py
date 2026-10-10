"""Independent process readback used by export acceptance; no resume, no writes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Api

if __name__ == '__main__':
    api = Api(sys.argv[1], sys.argv[2], location_locked=True)
    print(json.dumps({'state': api.get_state(), 'report': api.get_history()}, ensure_ascii=False))
