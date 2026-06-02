from src.engine.advanced_trailing_stop import AdvancedTrailingStopMonitor, simulate_trailing_stop_example


def test_long_activation_and_callback_exit():
    monitor = AdvancedTrailingStopMonitor(entry_price=100.0, leverage=10.0, side="Buy", callback_pct=2.0)

    monitor.update_price(100.0)
    activation = monitor.update_price(110.0)
    assert activation.trailing_armed is True
    assert round(activation.activation_price, 6) == 110.0
    assert round(activation.floor_price or 0, 6) == 110.0
    assert activation.should_close is False

    monitor.update_price(115.0)
    exit_tick = monitor.update_price(112.7)
    assert round(exit_tick.effective_trigger_price or 0, 6) == 112.7
    assert exit_tick.should_close is True


def test_long_floor_prevents_close_below_100_roi():
    monitor = AdvancedTrailingStopMonitor(entry_price=100.0, leverage=10.0, side="Buy", callback_pct=2.0)

    monitor.update_price(100.0)
    monitor.update_price(110.0)
    monitor.update_price(110.5)
    exit_tick = monitor.update_price(109.9)

    assert round(exit_tick.floor_price or 0, 6) == 110.0
    assert round(exit_tick.effective_trigger_price or 0, 6) == 110.0
    assert exit_tick.should_close is True


def test_short_activation_and_callback_exit():
    monitor = AdvancedTrailingStopMonitor(entry_price=100.0, leverage=10.0, side="Sell", callback_pct=2.0)

    monitor.update_price(100.0)
    activation = monitor.update_price(90.0)
    assert activation.trailing_armed is True
    assert round(activation.activation_price, 6) == 90.0
    assert round(activation.floor_price or 0, 6) == 90.0
    assert activation.should_close is False

    monitor.update_price(85.0)
    exit_tick = monitor.update_price(86.7)
    assert round(exit_tick.effective_trigger_price or 0, 6) == 86.7
    assert exit_tick.should_close is True


def test_simulation_example_emits_long_and_short_events():
    events = simulate_trailing_stop_example()
    labels = {label for label, _ in events}
    assert labels == {"long", "short"}
    assert any(snapshot.should_close for _, snapshot in events)
