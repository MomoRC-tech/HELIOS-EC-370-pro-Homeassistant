Tests and local harness

Pytest unit tests
- Requires Python 3.10+ and pytest installed in your environment.
- Run just the parser tests:

```powershell
pytest -q tests\test_parser_var3a.py
```

Fake Helios TCP bridge (no hardware needed)
- Starts a TCP server on 0.0.0.0:8234 that emits pings every ~250ms and a Var_3A frame every 2s.
- Use it with the integration pointed at your host IP and port 8234.

```powershell
python .\scripts\fake_helios_bridge.py
```

Notes
- Frames use the same checksum as the integration ((sum(data)+1)&0xFF).
- Var_3A payload contains 10 words (LE, signed), interpreted as 0.1°C increments; the client maps indices 1..4 to temp_outdoor, temp_extract, temp_exhaust, temp_supply.
