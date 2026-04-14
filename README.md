# Nixos Network

## The beginning of a home journey and automation

## Installation process

### VM 

#### UTM Config



#### Partitioning

* Create your VM with the correct ISO Image attached
* Load DE Keys

```
sudo loadkeys de
```

* switch do root user

```
sudo -i
```

* Naivgate to the TMP Folder and pull the git repository

```
cd /tmp
git clone https://github.com/btwtill/Nixos
```

* Now partition your disk with the disko command

```
sudo nix --experimental-features "nix-command flakes" run github:nix-community/disko -- --mode destroy,format,mount ./Nixos/nixos-config/hosts/vm/disko.nix
```

#### NixOs install

* create tmp directory for install

```
mkdir -p /mnt/tmp
```

* Install the flake config

```
TMPDIR=/mnt/tmp nixos-install --flake /tmp/Nixos/nixos-config#vm
```