# -*- mode: ruby -*-
# vi: set ft=ruby :

require 'yaml'

config_file = File.exist?(File.join(__dir__, 'config.yml')) ? YAML.load_file(File.join(__dir__, 'config.yml')) : {}

VM_NAME   = config_file.dig('vm', 'name')   || "omniagent-vm"
VM_MEMORY = config_file.dig('vm', 'memory') || 4096
VM_CPUS   = config_file.dig('vm', 'cpus')   || 2
VM_DISK   = config_file.dig('vm', 'disk')   || "50GB"

Vagrant.configure("2") do |config|
  # ── Base Box ─────────────────────────────────────────────────────────
  config.vm.box = "generic/ubuntu2204"

  unless File.exist?(File.join(__dir__, '.vagrant/machines/default/hyperv/id'))
    # ── Primary Disk ─────────────────────────────────────────────────────
    config.vm.disk :disk, size: VM_DISK, primary: true
  end

  # ── No Host File Sharing (security) ─────────────────────────────────
  config.vm.synced_folder ".", "/vagrant", disabled: true

  # ── VM Resources ────────────────────────────────────────────────────
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

  # ── Network ─────────────────────────────────────────────────────────
  config.vm.provider "virtualbox" do |_vb, override|
    override.vm.network "private_network", type: "dhcp"
  end

  # ── SSH ─────────────────────────────────────────────────────────────
  config.ssh.forward_agent = false
  config.ssh.insert_key = true

  # ── Install Docker Engine + Compose ─────────────────────────────────
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

  # ── Clone Repo + Run Startup ───────────────────────────────────────
  config.vm.provision "shell", name: "setup-omniagent", privileged: true, inline: <<-SHELL
    set -euxo pipefail

    sleep 2

    # Clone this repo
    if [ ! -d /opt/omniagent ]; then
      git clone https://github.com/nexuslbs/omniagent.git /opt/omniagent
    fi

    # Run the startup script
    bash /opt/omniagent/scripts/startup.sh
  SHELL

  # ── Mattermost Setup (conditional on .env credentials) ──────────────
  config.vm.provision "shell", name: "setup-mattermost", privileged: true, inline: <<-SHELL
    set -euxo pipefail

    ENV_FILE="/opt/omni-stack/.env"

    # Only proceed if .env exists and has Mattermost credentials
    if [ ! -f "$ENV_FILE" ]; then
      echo "SKIP: No .env found at $ENV_FILE — Mattermost setup skipped"
      exit 0
    fi

    # Source the .env (safe subset: only the vars we need)
    ADMIN_PASS=$(grep -m1 '^MATTERMOST_ADMIN_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    TEST_PASS=$(grep -m1 '^MATTERMOST_TEST_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    BOT_PASS=$(grep -m1 '^MATTERMOST_BOT_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)

    if [ -z "$ADMIN_PASS" ] && [ -z "$TEST_PASS" ] && [ -z "$BOT_PASS" ]; then
      echo "SKIP: No Mattermost credentials found in .env"
      echo "  Define at least one of MATTERMOST_ADMIN_PASSWORD,"
      echo "  MATTERMOST_TEST_PASSWORD, or MATTERMOST_BOT_PASSWORD"
      exit 0
    fi

    echo "Mattermost credentials found — running setup..."

    COMPOSE="docker compose -f /opt/omni-stack/docker-compose.yml --profile manual"

    # Start the toolbox container (idles until stopped)
    $COMPOSE up -d toolbox --wait 2>/dev/null || $COMPOSE up -d toolbox

    # Run the setup script inside the toolbox
    $COMPOSE exec -T toolbox python3 /opt/omni-stack/scripts/mm-setup.py \
      --env-file "$ENV_FILE"

    # Stop the toolbox when done
    $COMPOSE down
  SHELL
end
