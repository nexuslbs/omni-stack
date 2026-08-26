# -*- mode: ruby -*-
# vi: set ft=ruby :

require 'yaml'

config_file = File.exist?(File.join(__dir__, 'config.yml')) ? YAML.load_file(File.join(__dir__, 'config.yml')) : {}

VM_NAME   = config_file.dig('vm', 'name')   || "omniagent-vm"
VM_MEMORY = config_file.dig('vm', 'memory') || 4096
VM_CPUS   = config_file.dig('vm', 'cpus')   || 2
VM_DISK   = config_file.dig('vm', 'disk')   || "50GB"
REPO_URL  = config_file.dig('repo')         || "https://github.com/nexuslbs/omni-stack"
require 'openssl'
require 'base64'
require 'json'
require 'net/http'
require 'uri'

# Mint a fresh GitHub App installation token (1h lifespan) from the org app's
# private key using only Ruby stdlib (works in Vagrant's embedded Ruby - no
# gems). The private key never leaves the host; only the short-lived token is
# passed to the VM provisioner via env.
def generate_installation_token(app_id, installation_id, key_path)
  key = OpenSSL::PKey::RSA.new(File.read(key_path))
  now = Time.now.to_i
  b64url = ->(data) { Base64.urlsafe_encode64(data).tr('=', '') }
  signing_input = "#{b64url.call({ alg: 'RS256', typ: 'JWT' }.to_json)}.#{b64url.call({ iat: now - 60, exp: now + 600, iss: app_id.to_s }.to_json)}"
  sig = b64url.call(key.sign(OpenSSL::Digest::SHA256.new, signing_input))
  jwt = "#{signing_input}.#{sig}"

  uri = URI("https://api.github.com/app/installations/#{installation_id}/access_tokens")
  req = Net::HTTP::Post.new(uri)
  scheme = 'Bearer'
  req['Authorization'] = "#{scheme} #{jwt}"
  req['Accept'] = 'application/vnd.github+json'
  req['User-Agent'] = 'omni-vagrant'
  req['Content-Type'] = 'application/json'
  req.body = '{}'
  res = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 30, read_timeout: 30) do |http|
    http.request(req)
  end
  raise "GitHub token request failed: HTTP #{res.code} #{res.body}" unless res.code == '201'
  JSON.parse(res.body)['token']
end

# Clone credential resolution:
#   1. config.yml `repo_token` (static PAT) - if set, it wins.
#   2. GitHub App auto-mint (config.yml github_app_id + github_installation_id
#      + github_app_private_key): a FRESH token is minted on every vagrant run,
#      so provisioning never fails from an expired token.
#   3. Neither - plain/SSH clone.
app_key_path = File.join(__dir__, config_file.dig('github_app_private_key') || '')
REPO_TOKEN = if config_file.dig('repo_token').to_s != ''
               config_file.dig('repo_token')
             elsif config_file.dig('github_app_id').to_s != '' &&
                   config_file.dig('github_installation_id').to_s != '' &&
                   File.exist?(app_key_path)
               generate_installation_token(config_file.dig('github_app_id'),
                                           config_file.dig('github_installation_id'),
                                           app_key_path)
             else
               if config_file.dig('github_app_id').to_s != '' && !File.exist?(app_key_path)
                 warn "config.yml: github_app_private_key file not found at #{app_key_path} - falling back to unauthenticated clone"
               end
               ''
             end

Vagrant.configure("2") do |config|
  #  Base Box 
  config.vm.box = "generic/ubuntu2204"

  unless File.exist?(File.join(__dir__, '.vagrant/machines/default/hyperv/id'))
    #  Primary Disk 
    config.vm.disk :disk, size: VM_DISK, primary: true
  end

  #  No Host File Sharing (security) 
  config.vm.synced_folder ".", "/vagrant", disabled: true

  #  VM Resources 
  config.vm.provider "virtualbox" do |vb|
    vb.memory = VM_MEMORY.to_i
    vb.maxmemory = VM_MEMORY.to_i
    vb.cpus   = VM_CPUS.to_i
    vb.name   = VM_NAME
  end

  config.vm.provider "hyperv" do |hv|
    hv.memory = VM_MEMORY.to_i
    hv.maxmemory = VM_MEMORY.to_i
    hv.cpus   = VM_CPUS.to_i
    hv.vmname = VM_NAME
    hv.enable_enhanced_session_mode = false
  end

  #  Network 
  config.vm.provider "virtualbox" do |_vb, override|
    override.vm.network "private_network", type: "dhcp"
  end

  #  SSH 
  config.ssh.forward_agent = true
  config.ssh.insert_key = true

  #  Install Docker Engine + Compose 
  config.vm.provision "shell", name: "install-docker", privileged: true, inline: <<-SHELL
    set -euxo pipefail

    # Install prerequisites
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl git

    # Add Docker's official GPG key and repository
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \\
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \\
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \\
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine, CLI, containerd, and Compose plugin
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add vagrant user to docker group
    usermod -aG docker vagrant

    # Enable and start Docker
    systemctl enable docker
    systemctl start docker

    # Verify installation
    docker --version
    docker compose version
  SHELL

  #  Clone Repo + Pull/Build Core Images 
  config.vm.provision "shell", name: "setup-omniagent", privileged: true,
    env: { "REPO_URL" => REPO_URL, "REPO_TOKEN" => REPO_TOKEN }, inline: <<-'SHELL'
    set -euxo pipefail

    sleep 2

    # Cleanup guard: remove the askpass helper. It contains no secrets - the
    # token lives only in the environment, never in a file, git config, the
    # clone URL, /opt/omni/.git/config, or the provision log.
    trap 'rm -f /tmp/git-askpass.sh' EXIT

    # Clone the configured repo (config.yml `repo` key) into /opt/omni.
    # Private-repo auth:
    #   - SSH URL (repo: git@github.com:nexuslbs/<repo>.git): uses the
    #     forwarded SSH agent (config.ssh.forward_agent = true).
    #   - HTTPS + config.yml `repo_token` (GitHub PAT): authenticated via
    #     GIT_ASKPASS - git invokes a tiny helper script with the login prompt
    #     and reads the answer from it; the token is read from the environment
    #     at runtime (env: {...} on the provisioner).
    clone_or_update() {
      local url="${1:-}" token="${2:-}"
      [ -n "$url" ] || { echo "ERROR: repo URL is empty (set the 'repo' key in config.yml)" >&2; exit 1; }
      if [ ! -d /opt/omni ]; then
        case "$url" in
          git@*|ssh://*)
            echo "Cloning via SSH (agent forwarding): ${url}"
            git clone "${url}" /opt/omni
            ;;
          https://*)
            if [ -n "${token}" ]; then
              echo "Cloning private repo over HTTPS with token auth..."
              set +x
              # GIT_ASKPASS: git calls this script with the prompt
              # ("Username for ..." / "Password for ...") and reads the reply.
              # The script holds no secrets - REPO_TOKEN is read from the
              # environment at call time.
              cat > /tmp/git-askpass.sh <<'ASKPASS'
#!/bin/sh
case "$1" in
  Username*) echo "x-access-token" ;;
  Password*) echo "$REPO_TOKEN" ;;
  *) exit 1 ;;
esac
ASKPASS
              chmod 700 /tmp/git-askpass.sh
              export GIT_ASKPASS=/tmp/git-askpass.sh
              export GIT_TERMINAL_PROMPT=0
              # Validate the token against the GitHub API before cloning.
              # Prints only the HTTP status code - the token is never echoed.
              if command -v curl >/dev/null 2>&1 && [[ "${url}" == https://github.com/* ]]; then
                repo_slug="${url#https://github.com/}"
                repo_slug="${repo_slug%.git}"
                api_code="$(curl -s -o /dev/null -w '%{http_code}' --oauth2-bearer "${token}" -H 'Accept: application/vnd.github+json' -H 'User-Agent: omni-bootstrap' "https://api.github.com/repos/${repo_slug}" || echo 000)"
                case "${api_code}" in
                  200) echo "Token check OK: can read ${repo_slug}" ;;
                  401|404)
                    echo "ERROR: GitHub token rejected (API ${api_code}) - invalid, expired, or no access to ${repo_slug}. Check the 'repo_token' value in config.yml." >&2
                    exit 1
                    ;;
                  *)   echo "WARN: token check returned HTTP ${api_code} - continuing anyway" >&2 ;;
                esac
              fi
              set -x
              git clone "${url}" /opt/omni
            else
              echo "Cloning (public or pre-authenticated): ${url}"
              git clone "${url}" /opt/omni
            fi
            ;;
          *)
            echo "Cloning: ${url}"
            git clone "${url}" /opt/omni
            ;;
        esac
      else
        echo "/opt/omni already exists - pulling latest"
        git -C /opt/omni pull --ff-only || true
      fi
    }

    # Call with xtrace OFF so the token never appears in the provision log
    # (set -x would print it in the `local url=... token=...` trace line).
    set +x
    clone_or_update "${REPO_URL}" "${REPO_TOKEN}"
    set -x

    cd /opt/omni

    # Pull + build ONLY the core (non-profiled) services. Profiled services
    # (mattermost, paperclip, noop, observability, ...) are opt-in: the
    # operator enables them later via COMPOSE_PROFILES / .env.
    CORE_SERVICES=$(docker compose config --services)
    docker compose pull ${CORE_SERVICES}
    docker compose build ${CORE_SERVICES}

    echo
    echo "Core images ready. Next steps (operator):"
    echo "  1. cp .env.example .env  (fill in POSTGRES_PASSWORD etc.)"
    echo "  2. docker compose up -d  (core)  or add --profile mattermost etc."
  SHELL
end
