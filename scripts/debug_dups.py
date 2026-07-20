import json, urllib.request

resp = json.loads(urllib.request.urlopen('http://localhost:8080/api/plugins').read())
data = resp.get('data', [])
if isinstance(data, list):
    plugins = data
elif isinstance(data, dict):
    plugins = []
    for key in ['tools', 'platforms', 'providers']:
        if key in data:
            plugins.extend(data[key])
else:
    plugins = []

# Count by name/source/status/is_duplicated
combos = {}
for p in plugins:
    key = (p.get('name'), p.get('source'), p.get('status'), p.get('is_duplicated'))
    combos[key] = combos.get(key, 0) + 1

print('Entry count by (name, source, status, is_duplicated):')
for k, v in sorted(combos.items()):
    print(f'  {k}: {v}')
