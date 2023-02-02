FROM fedora:37

WORKDIR /root

COPY setup-wireguard.py /root
COPY requirements.txt /root
RUN dnf -y install python3-pip && \
    pip3 install -r requirements.txt && \
    chmod +x setup-wireguard.py

ENTRYPOINT ["/root/setup-wireguard.py"]

