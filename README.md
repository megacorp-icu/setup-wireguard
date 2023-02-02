# Megacorp.icu wireguard mesh creation utility

This program will help create a wireguard mesh between any number of servers. This tool is not particularly useful if what you want to set up a VPN from your client. It is, however, very useful to create an encrypted link between a set of servers without a single point of failure. That is; as long as two servers are up they can communicate with each other. There is no central point of failure for the mesh.

The program will create a set of configuration files which can then be copied to any Linux system with wireguard support and systemd-networkd installed of version 237 or newer. The program keeps track of the current state of the mesh, generate and keep track of keys, and can add new nodes or remove old nodes from the mesh without worrying about the wireguard specifics too much.

## Installation

On a sufficiently modern Linux system with pip and python3 installed the following will install the required dependencies:

`$ pip install -r requirements.txt`

A Dockerfile is also provided:

`$ docker build . -t setup-wireguard`

or for podman users

`$ podman build . -t setup-wireguard`

## Usage

The basic workflow is:

 * Create a site configuration YAML file
 * Run the program
 * Copy the resulting configuration files to the hosts
 * (Re)start systemd-networkd on the hosts
 * Testing

After the program has ran the site configuration YAML file will be updated with wireguard keys and addresses in the new wireguard network. To ensure that hosts can easily be added and removed from the mesh at a later time be sure to keep your new site configuration yaml file backed up in a secure location.

### The site configuration yaml file

You can use the provided example yaml file and modify it suit your needs.

```
network:
  wireguard_subnet: 10.10.10.0/24
  wireguard_port: 51871
hosts:
  one.megacorp.icu:
    public_ipv4: 192.168.122.250
  two.megacorp.icu:
    public_ipv4: 192.168.122.28
  three.megacorp.icu:
    public_ipv4: 192.168.122.81

```

This example site configuration will create a new network `10.10.10.0/24` on the hosts one, two, and three. It is important to make sure that if this program is used in an existing environment that the network does not overlap with existing subnets.

### Running the program

The program only takes two command line options:

 * `-f / --file <path/to/site/yml>`
 * `-o / --output <path/to/output/directory>`

Assuming the site configuration yaml file is called `site-config.yml` and we want the wireguard configuration files in the directory `config` in the current directory:

`./setup-wireguard.py -f site-config.yml -o config`

or through docker:

`docker run -it --rm -v .:/data:z setup-wireguard -f /data/site-config.yml -o /data/config`

or podman:

`podman run -it --rm -v .:/data:z setup-wireguard -f /data/site-config.yml -o /data/config`

After running the program the site-config.yml file will look something like the following:

```
network:
  wireguard_subnet: 10.10.10.0/24
  wireguard_port: 51871
hosts:
  one.megacorp.icu:
    public_ipv4: 192.168.122.250
    wireguard_ipv4: 10.10.10.1
    wireguard_public_key: RCBe9x2jHLLNguCPoDon5pz1TY11f8ZAI0aX4OFRIA0=
    wireguard_private_key: 0PxkyCWFF9hvv+Er3W9Z3wOHgoigbotBMtc6MIdpnU0=
  two.megacorp.icu:
    public_ipv4: 192.168.122.28
    wireguard_ipv4: 10.10.10.2
    wireguard_public_key: 2BirkSVce7yPrnD0n0IjEMDh3kJS9wSzPxcnxsmRkCc=
    wireguard_private_key: aGm3rolX6QtagfdLRsr9qXqZ/+5hmKHDPM6pBv9TZ04=
  three.megacorp.icu:
    public_ipv4: 192.168.122.81
    wireguard_ipv4: 10.10.10.3
    wireguard_public_key: rr9HakYHHRPhywldty/Jgdk/5ZfUF+iAKMzc62iiU2w=
    wireguard_private_key: ABkiQLxanP3iUWoH6uVEq3nOkVSWiuMjyDTS/Vu2zUs=
mesh_keys:
  one.megacorp.icu:
    two.megacorp.icu: JxqEPVNVMZZt5mSZm9lbD7R1ZyqgNZMZlchKg+pZbnM=
    three.megacorp.icu: 89m8gC854P8cm7UVaF7b0zKjWFN2ellkfAL3jlsuHiA=
  two.megacorp.icu:
    three.megacorp.icu: t9UDKvh8QzTenC0t2WPJPQ+6HoxbiB13PvFHDnX/Mg8=
```

It is safe to edit this file if for instance the assigned network addresses are not what was expected. It is also possible to supply your own wireguard keys instead of the ones generated. Be sure to re-run the program after making such changes to ensure that the generated configuration files are updated!

The configuration files are now located in the directory `config/`. The following files will have been created:

```
config/one.megacorp.icu/wg0.network
config/one.megacorp.icu/wg0.netdev
config/two.megacorp.icu/wg0.network
config/two.megacorp.icu/wg0.netdev
config/three.megacorp.icu/wg0.network
config/three.megacorp.icu/wg0.netdev
```

### Copy the resulting configuration files to the hosts

The generated configuration files should be placed on their respective hosts in the `/etc/systemd/network` directory. So the files in `config/one.megacorp.icu/` should be placed in `/etc/systemd/network` on the host `one.megacorp.icu`.

If the hosts are resolvable on your local machine the files can be copied with a simple bash loop:

`pushd config ; for host in *; do scp ${host}/* root@${host}:/etc/systemd/network; done ; popd`

### (Re)start systemd-networkd on the hosts

After the configuration files have been copied systemd-networkd needs to be restarted and automatically started at boot. On each host the following commands should be executed:

```
systemctl enable systemd-networkd
systemctl restart systemd-networkd
```
Thus will enable and start systemd-networkd regardless of the state of the system.

### Testing

It should now be possible to log in to one.megacorp.icu and ping two.megacorp.icu:

```
[root@one ~]# ping -c 4 10.10.10.2
PING 10.10.10.2 (10.10.10.2) 56(84) bytes of data.
64 bytes from 10.10.10.2: icmp_seq=1 ttl=64 time=1.05 ms
64 bytes from 10.10.10.2: icmp_seq=2 ttl=64 time=1.50 ms
64 bytes from 10.10.10.2: icmp_seq=3 ttl=64 time=1.38 ms
64 bytes from 10.10.10.2: icmp_seq=4 ttl=64 time=0.638 ms

--- 10.10.10.2 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3005ms
rtt min/avg/max/mdev = 0.638/1.142/1.503/0.335 ms
```