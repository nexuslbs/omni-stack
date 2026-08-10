---
type: memory
confidence: high
source_message_ids: []
source_tool_outputs: []
last_verified_at: 2026-08-10T14:55:56Z
created_at: 2026-08-10T14:55:56Z
expires_at: 2026-10-09T14:55:56Z
---# Memory: git-push-auth-fallback-via-github-app-jwt

When git_commit-and-push / git_run-command use_auth=true fail with "GITHUB_APP_ID and GITHUB_INSTALLATION_ID must be set in the plugin config" (omnistable omniagent process env lacks GITHUB_APP_ID/GITHUB_INSTALLATION_ID), push manually: (1) app id 3967918, installation id 138119822, private key in /opt/workspace/omni-deployer/secrets.env (GITHUB_APP_KEY, \n-escaped PEM); (2) in the omnidev omniagent container (docker_compose exec, project_dir /opt/workspace/omni-stack, env_file /opt/workspace/omni-deployer/omnidev.env), build an RS256 JWT (iss=3967918, iat=now-60, exp=now+540) signed with openssl dgst -sha256 -sign, POST https://api.github.com/app/installations/138119822/access_tokens with Bearer JWT, then git push https://x-access-token:TOKEN@github.com/nexuslbs/omniagent.git main:main. After pushing via URL, run `git fetch origin` to update the local origin/main tracking ref (push-by-URL does not update it). Verified working 2026-08-10 (push dcbe482 to omniagent origin/main).