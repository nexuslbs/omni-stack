import sys, os, json, urllib.request

WORKSPACE = '/opt/workspace/omni-stack'
BASE = 'http://localhost:8080/api'

# Check what the API shows for platforms
resp = json.loads(urllib.request.urlopen(f'{BASE}/plugins').read())
data = resp.get('data', {})
if isinstance(data, dict):
    platforms = data.get('platforms', [])
elif isinstance(data, list):
    platforms = [p for p in data if p.get('plugin_type') == 'platform']
else:
    platforms = []
print('Platforms from API:')
for p in platforms:
    print(f'  {p.get("name")} (source={p.get("source")}, status={p.get("status")})')

# Check bundled dirs
bundled_dir = f'{WORKSPACE}/plugins/platforms'
print(f'\nBundled plugins dir: {bundled_dir}')
if os.path.exists(bundled_dir):
    print(f'  Contents: {os.listdir(bundled_dir)}')
else:
    print(f'  Does not exist!')

# Check data_dir
data_platforms = '/opt/omni/plugins/platforms'
print(f'\nData dir platforms: {data_platforms}')
if os.path.exists(data_platforms):
    print(f'  Contents: {os.listdir(data_platforms)}')
else:
    print(f'  Does not exist!')

# Check builtin platforms
builtin_path = '/app/plugins/platforms'
print(f'\nBuiltin platforms: {builtin_path}')
if os.path.exists(builtin_path):
    print(f'  Contents: {os.listdir(builtin_path)}')
else:
    print(f'  Does not exist!')
