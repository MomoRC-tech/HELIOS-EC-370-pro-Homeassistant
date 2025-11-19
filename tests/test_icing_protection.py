"""Tests for icing protection initialization and 24h trigger counting."""
import time
from collections import deque
from helios_pro_ventilation.coordinator import HeliosCoordinator


def test_icing_protection_initialized_enabled():
    """Test that icing_protection_enabled defaults to True."""
    # Stub hass
    class FakeHass:
        def __init__(self):
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()

    hass = FakeHass()
    coord = HeliosCoordinator(hass)

    # Check defaults are set
    assert coord.icing_protection_enabled is True, "icing_protection_enabled should default to True"
    assert coord.data.get("icing_protection_active") is False, "icing_protection_active should start False"
    assert coord._icing_start_time is None, "_icing_start_time should start None"
    assert isinstance(coord._icing_trigger_ts, deque), "_icing_trigger_ts should be a deque"
    assert len(coord._icing_trigger_ts) == 0, "_icing_trigger_ts should start empty"
    assert coord.data.get("icing_triggers_24h") == 0, "icing_triggers_24h should start at 0"


def test_icing_protection_rising_edge_detection():
    """Test that rising edge (inactive→active) records a timestamp."""
    class FakeHass:
        def __init__(self):
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()

    hass = FakeHass()
    coord = HeliosCoordinator(hass)
    
    # Simulate icing protection transitioning from False to True
    coord.data["icing_protection_active"] = False
    
    # First update: still inactive (temp above threshold)
    coord.update_values({"temp_outdoor": 5.0, "fan_level": 1})
    assert len(coord._icing_trigger_ts) == 0, "No trigger should be recorded when inactive"
    
    # Set the start time to 11 minutes ago to trigger activation
    coord._icing_start_time = time.time() - 660  # 11 minutes ago
    
    # Second update: now temp below threshold for >10 min, fan at 0 (rising edge)
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is True, "Should be active now"
    assert len(coord._icing_trigger_ts) == 1, "One trigger should be recorded on rising edge"
    assert coord.data.get("icing_triggers_24h") == 1, "Counter should be updated to 1"
    
    # Third update: still active (no new trigger)
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    assert len(coord._icing_trigger_ts) == 1, "No new trigger when remaining active"


def test_icing_protection_24h_rolloff():
    """Test that timestamps older than 24h are purged."""
    class FakeHass:
        def __init__(self):
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()

    hass = FakeHass()
    coord = HeliosCoordinator(hass)
    
    # Add old timestamp (25 hours ago)
    now = time.time()
    old_ts = now - (25 * 3600)
    coord._icing_trigger_ts.append(old_ts)
    
    # Add recent timestamp (1 hour ago)
    recent_ts = now - 3600
    coord._icing_trigger_ts.append(recent_ts)
    
    # Update should purge old timestamp
    coord.update_values({"temp_outdoor": 5.0, "fan_level": 1})
    
    assert len(coord._icing_trigger_ts) == 1, "Old timestamp should be purged"
    assert coord._icing_trigger_ts[0] == recent_ts, "Recent timestamp should remain"
    assert coord.data.get("icing_triggers_24h") == 1, "Counter should reflect current count"


def test_icing_protection_multiple_triggers():
    """Test multiple activations are tracked correctly."""
    class FakeHass:
        def __init__(self):
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()

    hass = FakeHass()
    coord = HeliosCoordinator(hass)
    
    # First activation: set start time to 11 minutes ago, fan at 0
    coord._icing_start_time = time.time() - 660
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is True
    assert coord.data.get("icing_triggers_24h") == 1
    
    # Deactivate by raising temperature
    coord.update_values({"temp_outdoor": 5.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is False
    assert coord.data.get("icing_triggers_24h") == 1  # Count stays
    
    # Second activation
    coord._icing_start_time = time.time() - 660
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is True
    assert coord.data.get("icing_triggers_24h") == 2
    
    # Deactivate again
    coord.update_values({"temp_outdoor": 5.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is False
    
    # Third activation
    coord._icing_start_time = time.time() - 660
    coord.update_values({"temp_outdoor": 2.0, "fan_level": 0})
    assert coord.data.get("icing_protection_active") is True
    assert coord.data.get("icing_triggers_24h") == 3
