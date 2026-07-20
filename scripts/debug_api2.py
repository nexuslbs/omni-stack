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

# Show full detail for actions, fetch, hindsight
for target in ['actions', 'fetch', 'hindsight']:
    print(f'\n=== {target} ===')
    for p in plugins:
        if p.get('name') == target:
            print(f'  source: {p.get("source")}, status: {p.get("status")}, duplicated: {p.get("is_duplicated")}')
            print(f'  has_source_code: {p.get("has_source_code")}, needs_build: {p.get("needs_build")}')
            print(f'  is_duplicated: {p.get("is_duplicated")}')
            
# Also check how many total plugins
print(f'\nTotal plugins: {len(plugins)}')
print(f'Unique names: {len(set(p.get("name") for p in plugins))}')
