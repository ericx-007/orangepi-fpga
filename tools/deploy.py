"""Deploy the panel and a locally built SRAM image over password SSH."""
import argparse
import getpass
from pathlib import Path
import sys
import time
import paramiko

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', default='root')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--bitstream', type=Path, required=True)
    args = parser.parse_args()
    if not args.bitstream.is_file():
        parser.error('Build and adapt the bitstream before deploying')
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = Path.home() / '.ssh/known_hosts'
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    # Unknown or changed keys are rejected. Connect once with native ssh first.
    client.connect(args.host, port=args.port, username=args.user,
                   password=getpass.getpass('Board SSH password: '),
                   look_for_keys=False, allow_agent=False, timeout=20)
    client.get_transport().set_keepalive(20)

    def run(command):
        channel = client.get_transport().open_session()
        channel.exec_command(command)
        while True:
            if channel.recv_ready():
                sys.stdout.write(channel.recv(32768).decode(errors='replace'))
                sys.stdout.flush()
            if channel.recv_stderr_ready():
                sys.stderr.write(channel.recv_stderr(32768).decode(errors='replace'))
                sys.stderr.flush()
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(.05)
        if channel.recv_exit_status():
            raise RuntimeError('Remote command failed')

    try:
        run('mkdir -p /opt/fpga-panel/evidence')
        with client.open_sftp() as sftp:
            for name in ['server.py', 'index.html', 'test_transport.py']:
                sftp.put(str(ROOT / name), '/opt/fpga-panel/' + name)
            sftp.put(str(args.bitstream), '/opt/fpga-panel/panel.fs')
            sftp.put(str(ROOT / 'tools/program-sram.sh'), '/opt/fpga-panel/program-sram.sh')
            sftp.put(str(ROOT / 'tools/fpga-panel.service'), '/etc/systemd/system/fpga-panel.service')
        run('systemctl daemon-reload && bash /opt/fpga-panel/program-sram.sh && systemctl start fpga-panel.service')
        run('systemctl is-active fpga-panel.service')
        print('Deployment finished. Forward localhost:8088 through SSH; verify FPGA connected in the page.')
    finally:
        client.close()


if __name__ == '__main__':
    main()
