"""Tests for icing protection initialization and 24h counter logic."""
import sys
import os

# Ensure conftest stubs are loaded first
import conftest  # noqa: F401

import time
from collections import deque

from helios_pro_ventilation.coordinator import HeliosCoordinator


def test_icing_protection_initialization():
    """Test that icing protection attributes are initialized correctly."""
    # Create a mock hass object
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
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Verify icing_protection_enabled is True by default
    assert hasattr(coord, "icing_protection_enabled")
    assert coord.icing_protection_enabled is True
    
    # Verify icing_protection_active is False initially
    assert "icing_protection_active" in coord.data
    assert coord.data["icing_protection_active"] is False
    
    # Verify _icing_start_time is None
    assert hasattr(coord, "_icing_start_time")
    assert coord._icing_start_time is None
    
    # Verify _icing_trigger_ts is a deque
    assert hasattr(coord, "_icing_trigger_ts")
    assert isinstance(coord._icing_trigger_ts, deque)
    assert len(coord._icing_trigger_ts) == 0
    
    # Verify icing_triggers_24h is 0
    assert "icing_triggers_24h" in coord.data
    assert coord.data["icing_triggers_24h"] == 0


def test_icing_protection_rising_edge_detection():
    """Test that rising edge (inactive→active) is detected and timestamp is added."""
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
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Initially inactive
    assert coord.data["icing_protection_active"] is False
    assert len(coord._icing_trigger_ts) == 0
    
    # Simulate activation by directly setting the state
    coord.data["icing_protection_active"] = True
    
    # Call update_values to trigger the edge detection
    # First, simulate inactive state
    coord.data["icing_protection_active"] = False
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    
    # Now activate (simulating the 10-minute threshold being crossed)
    # We need to set _icing_start_time in the past
    coord._icing_start_time = time.time() - 700  # more than 10 minutes ago
    coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
    
    # Check that activation was detected
    assert coord.data["icing_protection_active"] is True
    assert len(coord._icing_trigger_ts) == 1
    assert coord.data["icing_triggers_24h"] == 1


def test_icing_protection_24h_rolloff():
    """Test that entries older than 24h are purged."""
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
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    now = time.time()
    
    # Add some timestamps: one old (>24h), one recent
    coord._icing_trigger_ts.append(now - 90000)  # ~25 hours ago
    coord._icing_trigger_ts.append(now - 3600)   # 1 hour ago
    coord._icing_trigger_ts.append(now - 100)    # recent
    
    # Update to trigger purging
    coord.data["icing_protection_active"] = False
    coord.update_values({"temp_outdoor": 10.0, "fan_level": 1})
    
    # Should have purged the old entry
    assert len(coord._icing_trigger_ts) == 2
    assert coord.data["icing_triggers_24h"] == 2
    
    # Verify the oldest remaining timestamp is not older than 24h
    assert coord._icing_trigger_ts[0] >= now - 86400


def test_icing_protection_counter_updates():
    """Test that counter updates correctly on each activation."""
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
                def get(self, entity_id):
                    class State:
                        state = "4.0"
                    return State()
            self.states = States()
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Simulate multiple activations
    for i in range(5):
        # Reset to inactive
        coord.data["icing_protection_active"] = False
        coord.update_values({"temp_outdoor": 10.0, "fan_level": 1})
        
        # Trigger activation
        coord._icing_start_time = time.time() - 700
        coord.update_values({"temp_outdoor": 3.0, "fan_level": 0})
        
        # Wait a bit between activations
        time.sleep(0.01)
    
    # Should have 5 activations recorded
    assert len(coord._icing_trigger_ts) == 5
    assert coord.data["icing_triggers_24h"] == 5


if __name__ == "__main__":
    test_icing_protection_initialization()
    print("✓ test_icing_protection_initialization passed")
    
    test_icing_protection_rising_edge_detection()
    print("✓ test_icing_protection_rising_edge_detection passed")
    
    test_icing_protection_24h_rolloff()
    print("✓ test_icing_protection_24h_rolloff passed")
    
    test_icing_protection_counter_updates()
    print("✓ test_icing_protection_counter_updates passed")
    
    print("\nAll tests passed!")
