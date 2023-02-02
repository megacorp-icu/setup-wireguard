#!/usr/bin/env python3

import os
import sys
import base64
import argparse
import ruamel.yaml
import configparser
from netaddr import IPAddress, IPNetwork, AddrFormatError
from python_wireguard import Key

yaml = ruamel.yaml.YAML()

def die(message):
    print(f"fatal: {message}", file=sys.stderr)
    sys.exit(1)

def str_representer(dumper, data):
    return dumper.represent_str(str(data))

yaml.representer.add_representer(IPAddress, str_representer)
yaml.representer.add_representer(IPNetwork, str_representer)
yaml.representer.add_representer(Key, str_representer)

class Network:
    def __init__(self, network):
        self.network = network
        self.assigned_addresses = []

    def add_ip(self, ip):
        if ip in self.assigned_addresses:
            die(f"IP address {str(ip)} double assigned in network {str(self.network)}")

        self.assigned_addresses.append(ip)

    def assign_ip(self):
        for ip in self.network.iter_hosts():
            if ip not in self.assigned_addresses:
                self.add_ip(ip)
                return ip

class SiteConfig:
    def __init__(self, site_config_file):
        self.wg_network = None
        self.hosts = None

        self.site_config_file = site_config_file
        self.read_config_file()
        self.parse_site_config()

    def open_file(self, filename, mode):
        try:
            file = open(filename, mode) 
        except FileNotFoundError:
            die(f"{self.site_config_file} does not exist")
        except PermissionError:
            die(f"{self.site_config_file} is not writable")
        except Exception as e:
            die(f"{self.site_config_file} load error: {e.message}")

        return file

    def parse_ip_address(self, name, address):
        try:
            return IPAddress(address)
        except AddrFormatError:
            die(f"{name} '{cidr}' is not a valid ip address")

    def parse_wg_key(self, name, key):
        try:
            return Key(key)
        except ValueError:
            die(f"{name} '{key}' is not a valid wireguard key")

    def parse_site_config(self):
        if "network" not in self.site_config:
            die(f"Error parsing site config, missing 'network' section")

        if "wireguard_subnet" not in self.site_config["network"]:
            die(f"Error parsing site config, no 'wireguard_subnet' defined in 'network' section")

        if "wireguard_port" not in self.site_config["network"]:
            die(f"Error parsing site config, no 'wireguard_port' defined in 'network' section")

        try:
            self.site_config["network"]["wireguard_subnet"] = IPNetwork(self.site_config["network"]["wireguard_subnet"])
            self.wg_network = self.site_config["network"]["wireguard_subnet"]
        except AddrFormatError:
            die(f"network/wireguard_subnet '{self.site_config['network']['wireguard_subnet']}' is not a valid network definition")

        try:
            self.site_config["network"]["wireguard_port"] = int(self.site_config["network"]["wireguard_port"])
            if self.site_config["network"]["wireguard_port"] < 1 or self.site_config["network"]["wireguard_port"] > 65535: raise ValueError
            self.wg_port = self.site_config["network"]["wireguard_port"]

        except ValueError:
            die(f"network/wireguard_port '{self.site_config['network']['wireguard_port']}' is not a valid port number")

        if "hosts" not in self.site_config:
            die(f"Error parsing site config, missing 'hosts' section")

        self.hosts = self.site_config["hosts"].items()

        for hostname, data in self.site_config["hosts"].items():
            if "public_ipv4" not in data:
                die(f"host {hostname} does not have a public_ipv4 address")

            data["public_ipv4"] = self.parse_ip_address(f"hosts/{hostname}/public_ipv4", data["public_ipv4"])

            if "wireguard_ipv4" in data and data["wireguard_ipv4"]:
                data["wireguard_ipv4"] = self.parse_ip_address(f"hosts/{hostname}/wireguard_ipv4", data["wireguard_ipv4"])
            else:
                data["wireguard_ipv4"] = None

            if "wireguard_public_key" in data and data["wireguard_public_key"]:
                data["wireguard_public_key"] = self.parse_wg_key(f"hosts/{hostname}/wireguard_public_key", data["wireguard_public_key"])
            else:
                data["wireguard_public_key"] = None

            if "wireguard_private_key" in data and data["wireguard_private_key"]:
                data["wireguard_private_key"] = self.parse_wg_key(f"hosts/{hostname}/wireguard_private_key", data["wireguard_private_key"])
            else:
                data["wireguard_private_key"] = None

        if "mesh_keys" not in self.site_config:
            self.site_config["mesh_keys"] = {}

        self.mesh_keys = self.site_config["mesh_keys"]

        for host, peers in self.mesh_keys.items():
            for peer, key in peers.items():
                peers[peer] = self.parse_wg_key(f"mesh_keys/{host}/{peer}", key)
        
    def read_config_file(self):
        with self.open_file(self.site_config_file, "r+") as file:
            try:
                self.site_config = yaml.load(file)
            except Exception as e:
                die(f"{self.site_config_file} parse error {e}")

    def write_config_file(self):
        with self.open_file(self.site_config_file, "w") as file:
            yaml.dump(self.site_config, file)

class Application:
    def __init__(self, configfile, configdir):
        self.config = SiteConfig(configfile)
        self.configdir = configdir
        self.network = Network(self.config.wg_network)

    def complete_config(self):
        for hostname, data in self.config.hosts:
            if not data["wireguard_ipv4"]:
                data["wireguard_ipv4"] = self.network.assign_ip()

            if not data["wireguard_private_key"] or not data["wireguard_public_key"]:
                data["wireguard_private_key"], data["wireguard_public_key"] = Key.key_pair()
            
            for peer, data in self.config.hosts:
                if peer == hostname: continue
                if peer in self.config.mesh_keys and hostname in self.config.mesh_keys[peer]: continue

                if hostname not in self.config.mesh_keys:
                    self.config.mesh_keys[hostname] = {}

                if peer in self.config.mesh_keys[hostname]: continue

                self.config.mesh_keys[hostname][peer] = Key(base64.b64encode(os.urandom(32)).decode("utf-8"))

        self.config.write_config_file()

    def dict_to_ini(self, data):
        ini = ""

        for section, values in data.items():
            if type(values) is dict:
                ini += f"[{section}]\n"
                for k, v in values.items():
                    ini += f"{k} = {v}\n"
                ini += "\n"

            if type(values) is list:
                for entries in values:
                    ini += f"[{section}]\n"
                    for k, v in entries.items():
                        ini += f"{k} = {v}\n"
                    ini += "\n"
        return ini

    def get_mesh_key(self, host, peer):
        if host in self.config.mesh_keys:
            if peer in self.config.mesh_keys[host]:
                return self.config.mesh_keys[host][peer]

        if peer in self.config.mesh_keys:
            if host in self.config.mesh_keys[peer]:
                return self.config.mesh_keys[peer][host]

        die(f"internal error, could not find psk for {host} <> {peer}")

    def generate_host_configs(self):
        for hostname, data in self.config.hosts:
            basedir = f"{self.configdir}/{hostname}"
            os.makedirs(basedir, exist_ok=True)

            network = {}
            network["Match"] = {}
            network["Match"]["Name"] = "wg0"
            network["Network"] = {}
            network["Network"]["Address"] = f"{str(data['wireguard_ipv4'])}/32"

            network["Route"] = {}
            network["Route"]["Destination"] = f"{str(self.config.wg_network)}"

            with open(f"{basedir}/wg0.network", "w+") as file:
                file.write(self.dict_to_ini(network))

            netdev = {}
            netdev["NetDev"] = {}
            netdev["NetDev"]["Name"]= "wg0"
            netdev["NetDev"]["Kind"] = "wireguard"
            netdev["NetDev"]["Description"] = f"wg server {str(self.config.wg_network)}"

            netdev["WireGuard"] = {}
            netdev["WireGuard"]["ListenPort"] = str(self.config.wg_port)
            netdev["WireGuard"]["PrivateKey"] = str(data["wireguard_private_key"])

            netdev["WireGuardPeer"] = []

            for peer, peer_data in self.config.hosts:
                if peer == hostname: continue

                wg_peer = {}
                wg_peer["PublicKey"] = peer_data["wireguard_public_key"]
                wg_peer["PresharedKey"] = self.get_mesh_key(hostname, peer)
                wg_peer["AllowedIPs"] = f"{str(peer_data['wireguard_ipv4'])}/32"
                wg_peer["Endpoint"] = f"{str(peer_data['public_ipv4'])}:{self.config.wg_port}"
                wg_peer["PersistentKeepalive"] = 25

                netdev["WireGuardPeer"].append(wg_peer)

            with open(f"{basedir}/wg0.netdev", "w+") as file:
                file.write(self.dict_to_ini(netdev))

    def run(self):
        self.complete_config()
        self.generate_host_configs()
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', required=True, help="Site configuration YAML file")
    parser.add_argument('-o', '--output', required=True, help="Output directory")
    args = parser.parse_args()

    app = Application(args.file, args.output)
    app.run()
