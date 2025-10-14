import os, io, re, time
from helios_pro_ventilation.debug.rs485_logger import Rs485Logger


class DummyHass:
    class Config:
        def path(self, p=""):
            return os.getcwd()

    def __init__(self):
        self.config = DummyHass.Config()


def _wait_for_writer():
    # tiny sleep to let worker thread flush
    time.sleep(0.05)


def test_html_header_footer_and_ping(tmp_path):
    hass = DummyHass()
    base = os.fspath(tmp_path)
    lg = Rs485Logger(hass, base_path=base)
    path = lg.start()
    try:
        # Emit a ping sequence: 4 bytes, b0 arbitrary, b1=b2=0, b3=checksum(b0,b1,b2)
        b0 = 0x12
        chk = ((b0 + 0 + 0) + 1) & 0xFF
        lg.on_rx(bytes([b0, 0x00, 0x00, chk]))
        _wait_for_writer()
    finally:
        lg.stop()

    # Verify file created under tmp_path and contains header/footer markers and a Ping row
    assert os.path.dirname(path) == base
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "<table>" in html and "</table>" in html
    assert "Legend:" in html
    assert re.search(r"<td class=\"kind\">Ping</td>", html)
    assert "Stopped:" in html and "Summary:" in html


def test_tx_known_styling_and_garbage_prev_context(tmp_path):
    hass = DummyHass()
    base = os.fspath(tmp_path)
    lg = Rs485Logger(hass, base_path=base)
    path = lg.start()
    try:
        # Craft a valid generic TX request frame to known var (0x3A) with empty payload
        # frame: [addr, cmd, plen, var, payload..., chk]; plen = 1 (var only)
        addr, cmd, plen, var = 0x11, 0x00, 0x01, 0x3A
        core = bytes([addr, cmd, plen, var])
        chk = ((sum(core) + 1) & 0xFF)
        frame = core + bytes([chk])
        lg.on_tx(frame)
        # Then some garbage
        lg.on_tx(b"\xDE\xAD\xBE\xEF")
        _wait_for_writer()
    finally:
        lg.stop()

    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    # Known TX rows should carry dir-tx class
    assert "class=\"cat-known dir-tx\"" in html or "class=\"dir-tx cat-known\"" in html
    # Garbage row must include previous frame hex as hex-prev and garbage bytes as hex-garbage
    assert "hex-prev" in html and "hex-garbage" in html
    # Direction cell should show the arrow for TX
    assert "→ TX" in html
