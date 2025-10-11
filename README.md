Helios EC‑Pro custom integration for Home Assistant

This custom component integrates Helios EC‑Pro ventilation units over a TCP bridge into Home Assistant. It exposes sensors and climate control, and sends commands within short “send slots” after pings seen on the RS‑485 bus.

## Debug: One‑shot var scan

This integration now includes a convenience switch to perform a one‑time scan of all known Helios variables and log their decoded values. It’s meant for diagnostics and development only.

- Entity name: “Debug: One-shot var scan”
- How it works: when you turn it on, it queues read requests for each `HeliosVar` at a minimum spacing of 500 ms. As responses come in, decoded values are logged at INFO level as lines starting with “HeliosDebug: …”. The switch turns itself off once the pass completes.
- Scope: general variable responses are logged. The special Var_3A temperature block is handled by the sensor pipeline and isn’t re-logged by the scanner.

Tip: to see the logs in the UI, set the integration log level to info or debug.

Example configuration.yaml snippet:

```yaml
logger:
	default: warning
	logs:
		custom_components.helios_pro_ventilation: info
```

If you don’t see the switch, reload the integration or restart Home Assistant after updating the custom component.
