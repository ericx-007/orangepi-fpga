"""Adapt expected silicon ID and CRC, retaining configuration payload bytes.

CRC framing follows YosysHQ/apicula apycula/bslib.py (MIT).
This is specific to the verified, uncompressed OPi MSOC B-version stream.
"""
from pathlib import Path
import hashlib
import json

def crc16(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'rtl/impl/pnr/panel.fs'
lines = p.read_text().splitlines()
indices = [i for i,l in enumerate(lines) if l and not l.startswith('//')]
header = bytearray()
frame_count = None
first_frame_index = None
for ordinal, index in enumerate(indices):
    raw = int(lines[index], 2).to_bytes(len(lines[index])//8, 'big')
    # V-series includes an A5C3 synchronization word after the preamble.
    # Neither the synchronization word nor SPI-address command enters CRC.
    if ordinal >= 4 and raw[0] != 0xD2:
        header.extend(raw)
    if raw[0] == 0x3B:
        frame_count = int.from_bytes(raw[2:], 'big')
        first_frame_index = ordinal+1
        break
assert frame_count and first_frame_index
prefix = header
for ordinal in range(first_frame_index, first_frame_index+frame_count):
    raw = bytes.fromhex(f'{int(lines[indices[ordinal]],2):0{len(lines[indices[ordinal]])//4}x}')
    stored = int.from_bytes(raw[-8:-6], 'little')
    calculated = crc16(prefix+raw[:-8])
    assert stored == calculated, f'Original frame {ordinal-first_frame_index} CRC differs: {stored:x} != {calculated:x}'
    prefix = raw[-6:]
old = (0x060000000001081B).to_bytes(8,'big')
new = (0x060000000011081B).to_bytes(8,'big')
assert header.count(old) == 1
header = header.replace(old,new)
id_index = next(i for i in indices[:first_frame_index] if lines[i] == ''.join(f'{b:08b}' for b in old))
lines[id_index] = ''.join(f'{b:08b}' for b in new)
fi = indices[first_frame_index]
raw = int(lines[fi],2).to_bytes(len(lines[fi])//8,'big')
new_crc = crc16(header+raw[:-8])
raw = raw[:-8] + new_crc.to_bytes(2,'little') + raw[-6:]
lines[fi] = ''.join(f'{b:08b}' for b in raw)
out = p.with_name('panel-board-id.fs')
out.write_text('\n'.join(lines)+'\n')
result = dict(original=str(p.relative_to(ROOT)), adapted=str(out.relative_to(ROOT)), frames_verified=frame_count,
              original_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
              adapted_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
              modifications=['expected ID 0001081B -> measured 0011081B','first frame CRC16/ARC'],
              configuration_payload='unchanged')
report_dir = ROOT / 'build'
report_dir.mkdir(exist_ok=True)
(report_dir / 'bitstream-adaptation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
