"""Tests for icing protection initialization and counter behavior."""
import time
from collections import deque
from helios_pro_ventilation.coordinator import HeliosCoordinator


def test_icing_protection_initialization():
    """Test that icing protection is initialized correctly."""
    # Create mock hass object
    class MockHass:
        def __init__(self):
            self.data = {}
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, key):
                    return None
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Verify icing protection is enabled by default
    assert coord.icing_protection_enabled is True, "icing_protection_enabled should be True by default"
    
    # Verify icing protection status is False at startup
    assert coord.data["icing_protection_active"] is False, "icing_protection_active should be False at startup"
    
    # Verify icing start time is None
    assert coord._icing_start_time is None, "_icing_start_time should be None at startup"
    
    # Verify rolling counter is initialized
    assert hasattr(coord, "_icing_trigger_ts"), "_icing_trigger_ts should exist"
    assert isinstance(coord._icing_trigger_ts, deque), "_icing_trigger_ts should be a deque"
    assert len(coord._icing_trigger_ts) == 0, "_icing_trigger_ts should be empty at startup"
    assert coord.data["icing_triggers_24h"] == 0, "icing_triggers_24h should be 0 at startup"


def test_icing_protection_trigger_tracking():
    """Test that icing protection activations are tracked correctly."""
    # Create mock hass object
    class MockHass:
        def __init__(self):
            self.data = {}
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, key):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Mock set_fan_level to avoid errors
    coord.set_fan_level = lambda x: None
    
    # Simulate temperature below threshold to start tracking
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 1})
    
    # Verify icing start time is set
    assert coord._icing_start_time is not None, "_icing_start_time should be set when temp is below threshold"
    
    # Still inactive (not 10 minutes yet)
    assert coord.data["icing_protection_active"] is False, "Should not be active yet"
    assert coord.data["icing_triggers_24h"] == 0, "Counter should still be 0"
    
    # Simulate 10+ minutes passing by backdating the start time
    coord._icing_start_time = time.time() - 601
    
    # Update values to trigger the check
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 1})
    
    # Now it should be active and counter should increment
    assert coord.data["icing_protection_active"] is True, "Should be active after 10 minutes"
    assert coord.data["icing_triggers_24h"] == 1, "Counter should increment to 1"
    assert len(coord._icing_trigger_ts) == 1, "Should have one trigger timestamp"


def test_icing_protection_24h_rolling_window():
    """Test that old triggers are purged from the rolling 24h window."""
    # Create mock hass object
    class MockHass:
        def __init__(self):
            self.data = {}
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, key):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    now = time.time()
    
    # Add some fake trigger timestamps
    # One from 25 hours ago (should be purged)
    coord._icing_trigger_ts.append(now - 90000)  # 25 hours
    # One from 23 hours ago (should remain)
    coord._icing_trigger_ts.append(now - 82800)  # 23 hours
    # One from 1 hour ago (should remain)
    coord._icing_trigger_ts.append(now - 3600)
    
    # Enable icing protection and trigger an update
    coord.icing_protection_enabled = True
    coord.update_values({"temp_outdoor": 10.0, "fan_level": 1})
    
    # Verify old timestamp was purged
    assert len(coord._icing_trigger_ts) == 2, "Old timestamp (>24h) should be purged"
    assert coord.data["icing_triggers_24h"] == 2, "Counter should reflect remaining timestamps"
    
    # Verify the oldest timestamp is at least recent
    assert coord._icing_trigger_ts[0] >= now - 86400, "All remaining timestamps should be within 24 hours"


def test_icing_protection_reset_on_temp_recovery():
    """Test that icing protection resets when temperature recovers."""
    # Create mock hass object
    class MockHass:
        def __init__(self):
            self.data = {}
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, key):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    coord.set_fan_level = lambda x: None
    
    # Simulate activation
    coord._icing_start_time = time.time() - 601
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 1})
    assert coord.data["icing_protection_active"] is True, "Should be active"
    
    # Temperature recovers above threshold
    coord.update_values({"temp_outdoor": 5.0, "fan_level": 1})
    
    # Verify reset
    assert coord.data["icing_protection_active"] is False, "Should be inactive after temp recovery"
    assert coord._icing_start_time is None, "_icing_start_time should be reset"


def test_icing_protection_reset_on_fan_change():
    """Test that icing protection resets when fan level changes from 0 to non-zero."""
    # Create mock hass object
    class MockHass:
        def __init__(self):
            self.data = {}
            class Loop:
                def call_soon_threadsafe(self, cb, *a, **kw):
                    try:
                        cb(*a, **kw)
                    except Exception:
                        pass
            self.loop = Loop()
            class States:
                def get(self, key):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    coord.set_fan_level = lambda x: None
    
    # Simulate activation with fan at level 1
    coord._icing_start_time = time.time() - 601
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 1})
    assert coord.data["icing_protection_active"] is True, "Should be active"
    
    # Simulate that icing protection has set fan to 0
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    assert coord.data["icing_protection_active"] is True, "Should still be active with fan at 0"
    
    # User manually changes fan level to non-zero (override icing protection)
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 2})
    
    # Verify reset
    assert coord.data["icing_protection_active"] is False, "Should be inactive after user changes fan from 0 to non-zero"


if __name__ == "__main__":
    test_icing_protection_initialization()
    test_icing_protection_trigger_tracking()
    test_icing_protection_24h_rolling_window()
    test_icing_protection_reset_on_temp_recovery()
    test_icing_protection_reset_on_fan_change()
    print("All tests passed!")
