#!/usr/bin/env python3
"""Fetch OWASP ASVS Level 1 requirements from GitHub and save to standards/asvs/level1.json"""
import json
import urllib.request
from pathlib import Path

ASVS_URL = "https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/docs_en/OWASP%20Application%20Security%20Verification%20Standard%204.0.3-en.json"

Path("standards/asvs").mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(ASVS_URL) as r:
    raw = json.loads(r.read())

# Extract L1 requirements only
requirements = []
for chapter in raw.get("Requirements", []):
    for section in chapter.get("Items", []):
        for req in section.get("Items", []):
            if req.get("L1", {}).get("Required"):
                requirements.append({
                    "id": req["Shortcode"],
                    "level": 1,
                    "text": req["Description"],
                    "cwe": req.get("CWE", []),
                    "section": chapter["ShortName"],
                })

output = {
    "source": "OWASP ASVS 4.0.3",
    "level": 1,
    "fetched": "2026-03-03",
    "requirements": requirements,
}
Path("standards/asvs/level1.json").write_text(json.dumps(output, indent=2))
print(f"Saved {len(requirements)} L1 requirements")
