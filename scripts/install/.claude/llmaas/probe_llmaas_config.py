import json
import sys
from pathlib import Path

project_root = Path(r"C:\Daten\Python\vobes_agent_vscode")
auth_utils_dir = Path(r"C:\Daten\Python\vobes_agent_vscode\.claude")
for p in (str(auth_utils_dir), str(project_root)):
    if p not in sys.path:
        sys.path.insert(0, p)

from auth_utils import get_base_url, get_api_client_id

print(json.dumps({
    "base_url": get_base_url(),
    "api_client_id": get_api_client_id(),
}), end="")
