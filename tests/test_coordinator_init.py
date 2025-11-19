"""Test coordinator initialization of icing protection flags."""

from helios_pro_ventilation.coordinator import HeliosCoordinator, HeliosCoordinatorWithQueue


def test_coordinator_icing_protection_initialization():
    """Test that icing protection flags are initialized to False on startup."""
    # Create a minimal hass mock
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
    
    hass = MockHass()
    
    # Test HeliosCoordinator
    coord = HeliosCoordinator(hass)
    
    # Verify icing_protection_enabled attribute is initialized
    assert hasattr(coord, "icing_protection_enabled"), "icing_protection_enabled attribute should exist"
    assert coord.icing_protection_enabled is False, "icing_protection_enabled should be False by default"
    
    # Verify icing_protection_active in data dict is initialized
    assert "icing_protection_active" in coord.data, "icing_protection_active should exist in data"
    assert coord.data["icing_protection_active"] is False, "icing_protection_active should be False by default"
    
    # Verify _icing_start_time is initialized
    assert hasattr(coord, "_icing_start_time"), "_icing_start_time attribute should exist"
    assert coord._icing_start_time is None, "_icing_start_time should be None by default"


def test_coordinator_with_queue_icing_protection_initialization():
    """Test that icing protection flags are initialized in HeliosCoordinatorWithQueue."""
    # Create a minimal hass mock
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
    
    hass = MockHass()
    
    # Test HeliosCoordinatorWithQueue (subclass)
    coord = HeliosCoordinatorWithQueue(hass)
    
    # Verify icing_protection_enabled attribute is initialized
    assert hasattr(coord, "icing_protection_enabled"), "icing_protection_enabled attribute should exist"
    assert coord.icing_protection_enabled is False, "icing_protection_enabled should be False by default"
    
    # Verify icing_protection_active in data dict is initialized
    assert "icing_protection_active" in coord.data, "icing_protection_active should exist in data"
    assert coord.data["icing_protection_active"] is False, "icing_protection_active should be False by default"
    
    # Verify _icing_start_time is initialized
    assert hasattr(coord, "_icing_start_time"), "_icing_start_time attribute should exist"
    assert coord._icing_start_time is None, "_icing_start_time should be None by default"


def test_icing_protection_switch_reads_initialized_value():
    """Test that the switch entity can read the initialized icing_protection_enabled value."""
    # Create a minimal hass mock
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
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Simulate what the switch entity does: getattr with False default
    value = getattr(coord, "icing_protection_enabled", False)
    assert value is False, "Switch should read False as the initial value"


def test_icing_protection_binary_sensor_reads_initialized_value():
    """Test that the binary sensor can read the initialized icing_protection_active value."""
    # Create a minimal hass mock
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
    
    hass = MockHass()
    coord = HeliosCoordinator(hass)
    
    # Simulate what the binary sensor does: read from coord.data
    value = coord.data.get("icing_protection_active")
    assert value is False, "Binary sensor should read False as the initial value"
    
    # The binary sensor also checks availability based on key presence
    assert "icing_protection_active" in coord.data, "Key should be present for availability check"
