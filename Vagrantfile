# -*- mode: ruby -*-
# vi: set ft=ruby :

require 'yaml'

config_file = File.exist?(File.join(__dir__, 'config.yml')) ? YAML.load_file(File.join(__dir__, 'config.yml')) : {}

VM_NAME   = config_file.dig('vm', 'name')   || "omniagent-vm"
VM_MEMORY = config_file.dig('vm', 'memory') || 4096
VM_CPUS   = config_file.dig('vm', 'cpus')   || 2
VM_DISK   = config_file.dig('vm', 'disk')   || "50GB"

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

  #  Provisioning
  #  The Vagrantfile no longer provisions the machine itself: all real setup
  #  (docker, node-exporter, repo clone, compose pull/build/up, secrets) lives
  #  in the remote setup.sh from the omni-stack repo. Here we only do the
  #  host-shape fixes that MUST happen before anything else:
  #    0. grow the root filesystem to the disk size configured in config.yml
  #       (`vm.disk`) - FIRST STEP, always (without it the VM fills up),
  #    1. disable swap permanently,
  #    2. stage the host-side files that exist next to this Vagrantfile
  #       (config.yml, .env, <key>.pem - the key file name is the
  #       `github_app_private_key` value in config.yml) into the VM,
  #    3. move them into /opt/secrets/, and
  #    4. if config.yml is present, run the omni-stack setup.sh via bash -
  #       ALWAYS the omni-stack setup, even when the repo in config.yml is a
  #       different repository.

  #  STEP 0 (MUST stay the FIRST provisioner): grow the disk.
  #  `config.vm.disk :disk, size: VM_DISK` only enlarges the virtual disk;
  #  the guest filesystem keeps the small box-image size until the GPT/MBR
  #  partition, the LVM physical volume and the root logical volume are grown.
  #  Without this the box runs out of space (docker images/builds fill it) and
  #  everything gets slow. Provisioners run as root, so no sudo is needed.
  config.vm.provision "shell", name: "grow-disk", privileged: true, inline: <<-'SHELL'
    set -euxo pipefail
    export DEBIAN_FRONTEND=noninteractive
    # cloud-guest-utils ships growpart; install it if the box image lacks it.
    if ! command -v growpart >/dev/null 2>&1; then
      apt-get update -qq
      apt-get install -y -qq cloud-guest-utils
    fi
    # Default generic/ubuntu2204 layout: /dev/sda3 is the LVM PV inside
    # ubuntu-vg (ubuntu-lv mounted on /). Grow partition -> PV -> LV -> fs.
    growpart /dev/sda 3 || true
    pvresize /dev/sda3 || true
    lvextend -l +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv --resizefs || true
    df -h /
  SHELL

  #  STEP 1 (MUST run before any container work): disable swap.
  #  The VM ended up with a huge swap file on the small disk; swapping made
  #  the whole machine (and the agent) pathologically slow while swapoff took
  #  ages / got OOM-killed. Disable swap now AND persistently (fstab).
  config.vm.provision "shell", name: "disable-swap", privileged: true, inline: <<-'SHELL'
    set -euxo pipefail
    swapoff -a || true
    if grep -Eq '^[^#]*[[:space:]]swap[[:space:]]' /etc/fstab; then
      cp -n /etc/fstab /etc/fstab.omni.bak || true
      sed -i -E '/^[^#].*[[:space:]]swap[[:space:]]/s/^/# omni: swap disabled /' /etc/fstab
    fi
    # Drop any systemd swap unit generated from the old fstab entry.
    systemctl daemon-reload || true
    systemctl --no-pager --type swap list-units || true
    free -m
  SHELL

  config.vm.provision "shell", name: "prepare-secrets-dir", privileged: true, inline: <<-SHELL
    set -euxo pipefail
    mkdir -p /tmp/omni-secrets /opt/secrets
    chown -R vagrant:vagrant /tmp/omni-secrets
  SHELL

  # Copy optional host-side files into the VM (only if present next to this
  # Vagrantfile). The private key is copied with its basename so setup.sh can
  # find it at /opt/secrets/<basename> (as configured via config.yml).
  secret_files = {}
  secret_files['config.yml'] = File.join(__dir__, 'config.yml') if File.exist?(File.join(__dir__, 'config.yml'))
  secret_files['.env']       = File.join(__dir__, '.env')       if File.exist?(File.join(__dir__, '.env'))
  key_name = config_file.dig('github_app_private_key')
  if key_name && !key_name.to_s.empty?
    key_path = File.join(__dir__, key_name)
    secret_files[File.basename(key_name)] = key_path if File.exist?(key_path)
  end
  secret_files.each do |name, src|
    config.vm.provision "file", source: src, destination: "/tmp/omni-secrets/#{name}"
  end

  config.vm.provision "shell", name: "setup-omni", privileged: true, inline: <<-'SHELL'
    set -euxo pipefail
    cp -fR /tmp/omni-secrets/. /opt/secrets/ 2>/dev/null || true
    if [ -f /opt/secrets/config.yml ]; then
      # Run the remote setup.sh from the omni-stack repo (bash). The setup
      # used is ALWAYS the omni-stack one, even when config.yml's repo key
      # points at a different repository.
      curl -fsSL https://raw.githubusercontent.com/nexuslbs/omni-stack/main/setup.sh -o /tmp/omni-setup.sh
      bash /tmp/omni-setup.sh
    else
      echo "No config.yml in /opt/secrets - skipping omni setup (docker + node-exporter not installed; run setup.sh manually after placing config files)"
    fi
  SHELL
end
