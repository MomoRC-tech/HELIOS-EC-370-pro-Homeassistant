"""Tests for HeliosCoordinator initialization, specifically icing protection defaults."""
import pytest

from helios_pro_ventilation.coordinator import HeliosCoordinator, HeliosCoordinatorWithQueue


class DummyHass:
    """Minimal stub for Home Assistant instance."""
    class Loop:
        def call_soon_threadsafe(self, *args, **kwargs):
            pass
    def __init__(self):
        self.loop = self.Loop()


def test_coordinator_icing_protection_defaults():
    """Verify that icing protection attributes are explicitly initialized to False/None."""
    hass = DummyHass()
    coord = HeliosCoordinator(hass)
    
    # Verify switch default state
    assert hasattr(coord, "icing_protection_enabled"), "icing_protection_enabled attribute should exist"
    assert coord.icing_protection_enabled is False, "icing_protection_enabled should default to False"
    
    # Verify binary sensor default state
    assert "icing_protection_active" in coord.data, "icing_protection_active should be in coordinator data"
    assert coord.data["icing_protection_active"] is False, "icing_protection_active should default to False"
    
    # Verify internal timer baseline
    assert hasattr(coord, "_icing_start_time"), "_icing_start_time attribute should exist"
    assert coord._icing_start_time is None, "_icing_start_time should default to None"


def test_coordinator_with_queue_icing_protection_defaults():
    """Verify icing protection defaults are also initialized in HeliosCoordinatorWithQueue."""
    hass = DummyHass()
    coord = HeliosCoordinatorWithQueue(hass)
    
    # Verify switch default state
    assert hasattr(coord, "icing_protection_enabled"), "icing_protection_enabled attribute should exist"
    assert coord.icing_protection_enabled is False, "icing_protection_enabled should default to False"
    
    # Verify binary sensor default state
    assert "icing_protection_active" in coord.data, "icing_protection_active should be in coordinator data"
    assert coord.data["icing_protection_active"] is False, "icing_protection_active should default to False"
    
    # Verify internal timer baseline
    assert hasattr(coord, "_icing_start_time"), "_icing_start_time attribute should exist"
    assert coord._icing_start_time is None, "_icing_start_time should default to None"


def test_icing_protection_enabled_can_be_toggled():
    """Verify that the icing_protection_enabled flag can be changed after initialization."""
    hass = DummyHass()
    coord = HeliosCoordinator(hass)
    
    # Start with False
    assert coord.icing_protection_enabled is False
    
    # Toggle to True
    coord.icing_protection_enabled = True
    assert coord.icing_protection_enabled is True
    
    # Toggle back to False
    coord.icing_protection_enabled = False
    assert coord.icing_protection_enabled is False


def test_icing_protection_active_can_be_updated():
    """Verify that icing_protection_active can be updated in coordinator.data."""
    hass = DummyHass()
    coord = HeliosCoordinator(hass)
    
    # Start with False
    assert coord.data["icing_protection_active"] is False
    
    # Update to True
    coord.data["icing_protection_active"] = True
    assert coord.data["icing_protection_active"] is True
    
    # Update back to False
    coord.data["icing_protection_active"] = False
    assert coord.data["icing_protection_active"] is False
