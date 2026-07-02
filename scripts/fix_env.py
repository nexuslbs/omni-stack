import re
with open('/opt/workspace/omni-stack/.env', 'r') as f:
    content = f.read()

# Fix the corrupted lines
lines = content.split('\n')
fixed = []
for line in lines:
    if line.startswith('MATTERMOST_ACCESS_TOKEN'):
        fixed.append('MATTERMOST_ACCESS_TOKEN=')
    # MATTERMOST_CHANNEL_IDS removed - channel discovery is auto-discovery via API
    else:
        fixed.append(line)

with open('/opt/workspace/omni-stack/.env', 'w') as f:
    f.write('\n'.join(fixed))

print("Fixed")
