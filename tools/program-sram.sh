set -eu
systemctl stop fpga-panel
trap 'modprobe ftdi_sio' EXIT
cd /opt/Gowin/Programmer/bin
set +e
timeout 70 ./programmer_cli --device GW5AT-138B --operation_index 2 --cable-index 1 --channel 0 --fsFile /opt/fpga-panel/panel.fs >/opt/fpga-panel/evidence/program.log 2>&1
result=$?
tr '\r' '\n' </opt/fpga-panel/evidence/program.log | tail -10
echo "programmer_exit=$result"
python3 - <<'PY'
from pathlib import Path
import re,sys
log=Path('/opt/fpga-panel/evidence/program.log').read_text(errors='replace')
codes=re.findall(r'Status Code is: 0x([0-9A-Fa-f]+)',log)
if not codes:
    sys.exit('No configuration status returned')
status=int(codes[-1],16)
if status & 15 or not status & (1<<13):
    sys.exit('FPGA configuration failed: '+hex(status))
print('FPGA DONE asserted, CRC/command/ID/timeout flags clear')
PY
