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
  #  in the remote setup.sh from the omni-stack repo. Here we only:
  #    1. stage the host-side files that exist next to this Vagrantfile
  #       (config.yml, .env, <key>.pem - the key file name is the
  #       `github_app_private_key` value in config.yml) into the VM,
  #    2. move them into /opt/secrets/, and
  #    3. if config.yml is present, run the omni-stack setup.sh via bash -
  #       ALWAYS the omni-stack setup, even when the repo in config.yml is a
  #       different repository.
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
    cp -f /tmp/omni-secrets/* /opt/secrets/ 2>/dev/null || true
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
