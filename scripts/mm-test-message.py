#!/usr/bin/env python3
"""Send a test message to Mattermost as testuser, then check for agent reply."""
import json, subprocess, time, sys

MM_URL = 'http://omm-mattermost:8065'
TOKEN = None

def api(method, path, data=None):
    cmd = ['curl', '-s', '-X', method, f'{MM_URL}{path}',
           '-H', 'Content-Type: application/json']
    if TOKEN:
        cmd += ['-H', f'Authorization: Bearer {TOKEN}']
    if data:
        cmd += ['-d', json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout) if r.stdout.strip() else {}

# Step 1: Login (use -D to capture token header)
hdrs = subprocess.run(['curl', '-s', '-D', '-', '-X', 'POST', f'{MM_URL}/api/v4/users/login',
    '-H', 'Content-Type: application/json',
    '-d', '{"login_id":"testuser","password":"TestPass123!"}'],
    capture_output=True, text=True, timeout=15)
for line in (hdrs.stderr + '\n' + hdrs.stdout).split('\n'):
    if line.lower().startswith('token:'):
        TOKEN = line.split(':', 1)[1].strip()
        break
print(f'1. Logged in. Token: {TOKEN[:20] if TOKEN else "FAIL"}...')

if not TOKEN:
    sys.exit(1)

# Step 2: Get teams
teams = api('GET', '/api/v4/teams')
print(f'2. Teams: {[t["name"] for t in teams]}')

# Step 3: Find setup channel and post
for team in teams:
    channels = api('GET', f'/api/v4/teams/{team["id"]}/channels')
    for c in channels:
        if c['name'] == 'setup':
            ch_id = c['id']
            print(f'3. Found channel: {c["name"]} (id: {ch_id})')
            
            # Post message
            result = api('POST', '/api/v4/posts',
                data={'channel_id': ch_id, 'message': 'hello, test message from testuser'})
            post_id = result.get('id')
            print(f'4. Posted message. ID: {post_id}')
            
            if post_id:
                # Step 4: Wait and check for agent reply
                print('5. Waiting 20s for agent reply...')
                time.sleep(20)
                
                # Get recent posts
                posts = api('GET', f'/api/v4/channels/{ch_id}/posts?per_page=50')
                all_posts = posts.get('posts', {})
                if isinstance(all_posts, dict):
                    ordered = sorted(all_posts.values(), key=lambda x: x.get('create_at', 0))
                    print(f'   Found {len(ordered)} posts:')
                    for p in ordered:
                        uid = p.get('user_id', '')[:12]
                        msg = p.get('message', '')[:300]
                        print(f'   [{uid}] {msg}')
                else:
                    print(f'   Posts format unexpected: {type(all_posts)}')
            break
    else:
        continue
    break

print('\nDone.')
