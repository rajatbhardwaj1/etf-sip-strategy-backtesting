import pandas as pd
from src.strategy import MovingAverageStrategy


def test_moving_average_signals():
    # Dummy data
    data = pd.DataFrame({
        "Close": [10, 11, 12, 11, 13, 14, 15, 16, 17, 18]
    })
    strategy = MovingAverageStrategy(short_window=2, long_window=3)
    signals = strategy.generate_signals(data)

    assert "signal" in signals.columns
    assert "position" in signals.columns
