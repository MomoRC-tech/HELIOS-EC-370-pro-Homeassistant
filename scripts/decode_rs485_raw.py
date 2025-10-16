from __future__ import annotations

import sys
import os
import json
import time
from typing import Any, Dict

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from helios_pro_ventilation.debug.rs485_logger import Rs485Logger  # type: ignore
from helios_pro_ventilation.const import HeliosVar  # type: ignore
from helios_pro_ventilation.parser import _decode_sequence  # type: ignore


def decode_raw(raw_path: str, out_html: str | None = None) -> str:
    if not os.path.exists(raw_path):
        raise FileNotFoundError(raw_path)
    # Create a dummy logger in HTML-only mode (without raw_only)
    # We will bypass worker thread and call internal HTML methods directly.
    logger = Rs485Logger(hass=None, base_path=out_html or raw_path.replace('.raw.jsonl', '.decoded.html'), raw_only=False)
    # Open the output file
    folder = os.path.dirname(logger._path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    logger._file = open(logger._path, 'w', encoding='utf-8')
    logger._write_html_header()

    # Iterate raw events and emit rows
    with open(raw_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj: Dict[str, Any] = json.loads(line)
            except Exception:
                continue
            ts = obj.get('ts') or time.strftime('%Y-%m-%dT%H:%M:%S')
            # Patch logger's ts method temporarily
            def _ts_override(ts_val: str = ts) -> str:
                return ts_val

            logger._ts = lambda: ts  # type: ignore

            kind = obj.get('kind')
            direction = obj.get('dir', 'RX')
            hex_data = bytes.fromhex(obj.get('data', '')) if isinstance(obj.get('data'), str) else b''

            if kind == 'ping':
                logger._write_row('ping', direction, 'ping ok', hex_data, var_label='')
            elif kind == 'broadcast':
                try:
                    logger._write_row('broadcast', direction, f'broadcast ok, plen={hex_data[2]}', hex_data, var_label='')
                except Exception:
                    logger._write_row('broadcast', direction, 'broadcast ok', hex_data, var_label='')
            elif kind == 'generic':
                # Decode variable and values like live logger
                try:
                    addr, cmd, plen = hex_data[0], hex_data[1], hex_data[2]
                    var_idx = hex_data[3]
                    payload = hex_data[4:-1]
                    chk = hex_data[-1]
                    is_reqresp = cmd in (0x00, 0x01)
                    var_name = None
                    label = None
                    values = None
                    try:
                        var = HeliosVar(var_idx)
                        var_name = var.name
                        values = _decode_sequence(payload, var)
                        label = f"{var_name}"
                    except Exception:
                        label = None
                    val_txt = ''
                    if isinstance(values, list) and values:
                        if len(values) <= 8:
                            val_txt = f" values={values}"
                        else:
                            val_txt = f" values={values[:8]}…({len(values)})"
                    # Suffix with TX/RX role when applicable
                    role_txt = (('TX' if direction == 'TX' else 'RX') if is_reqresp else 'frame') if label else ''
                    suffix = f" | {role_txt}: ID 0x{var_idx:02X} ({label})" if label else ''
                    tag = ('TX ok' if direction == 'TX' else 'RX ok') if is_reqresp else 'frame ok'
                    summary = f"{tag} addr=0x{addr:02X} cmd=0x{cmd:02X} var=0x{var_idx:02X} len={plen} chk=0x{chk:02X}{val_txt}{suffix}"
                    cat = 'known' if label is not None else 'unknown'
                    logger._write_row(cat, direction, summary, hex_data, var_label=(var_name or f"0x{var_idx:02X}"), var_idx=var_idx)
                except Exception:
                    logger._write_row('unknown', direction, 'frame ok', hex_data, var_label='')
            elif kind == 'ack':
                try:
                    addr, cmd, plen = hex_data[0], hex_data[1], hex_data[2]
                    var_idx = hex_data[3]
                    chk = hex_data[-1]
                    summary = f"ack ok addr=0x{addr:02X} cmd=0x{cmd:02X} var=0x{var_idx:02X} len={plen} chk=0x{chk:02X}"
                    # Try to resolve var name for display
                    try:
                        var = HeliosVar(var_idx)
                        var_name = var.name
                    except Exception:
                        var_name = None
                    logger._write_row('ack', direction, summary, hex_data, var_label=(var_name or f"0x{var_idx:02X}"), var_idx=var_idx)
                except Exception:
                    logger._write_row('ack', direction, 'ack ok', hex_data, var_label='')
            elif kind == 'garbage':
                prev_hex = obj.get('prev')
                combined_hex = ''
                if prev_hex:
                    try:
                        prev_bytes = bytes.fromhex(prev_hex)
                        combined_hex += f'<span class="hex hex-prev">{prev_bytes.hex(" ")}</span> '
                    except Exception:
                        combined_hex += f'<span class="hex hex-prev">{prev_hex}</span> '
                # Garbage itself (spaced)
                combined_hex += f'<span class="hex hex-garbage">{hex_data.hex(" ")}</span>'
                logger._write_row('garbage', direction, f'garbage ({len(hex_data)} bytes)', b'', hex_html=combined_hex, var_label='')
            else:
                # Unknown event kinds are ignored in offline decode
                pass

    logger._write_html_footer()
    try:
        logger._file.flush()
    except Exception:
        pass
    try:
        logger._file.close()
    except Exception:
        pass
    return logger._path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('Usage: python scripts/decode_rs485_raw.py <path-to-raw.jsonl> [output.html]')
        return 2
    raw = argv[1]
    out = argv[2] if len(argv) > 2 else None
    out_path = decode_raw(raw, out)
    print(out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
