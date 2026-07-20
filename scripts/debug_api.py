import sys, json, urllib.request

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

for p in plugins:
    if p.get('name') == 'actions':
        print('actions plugin:')
        print(f'  source: {p.get("source")}')
        print(f'  plugin_type: {p.get("plugin_type")}')
        print(f'  status: {p.get("status")}')
        
# Also check what source values are being returned for tools
print('\nAll tool plugins:')
for p in plugins:
    if p.get('plugin_type') == 'tool':
        print(f'  {p.get("name"):30s} source={p.get("source"):15s} status={p.get("status")}')
