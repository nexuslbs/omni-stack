import json, urllib.request

resp = json.loads(urllib.request.urlopen("http://localhost:8080/api/plugins").read())
data = resp.get("data", [])
if isinstance(data, list):
    for p in data:
        if p.get("name") == "test-rust-tool":
            print(json.dumps(p, indent=2, default=str))
elif isinstance(data, dict):
    for p in data.get("tools", []):
        if p.get("name") == "test-rust-tool":
            print(json.dumps(p, indent=2, default=str))
