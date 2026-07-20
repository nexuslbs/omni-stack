import json, urllib.request

resp = json.loads(urllib.request.urlopen("http://localhost:8080/api/plugins").read())
data = resp.get("data", [])
if isinstance(data, list):
    for p in data:
        if p.get("name") == "test-rust-tool":
            print("Source:", p.get("source"))
            print("Status:", p.get("status"))
            if p.get("remote"):
                print("Remote path:", p.get("remote").get("path"))
            print("Plugin dir:", p.get("plugin_dir", "N/A"))
