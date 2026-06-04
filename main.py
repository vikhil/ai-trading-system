from data_engine import DataEngine
from feature_engine import FeatureEngine
from signal_engine import SignalEngine
from scoring_engine import ScoringEngine
from pipeline import Pipeline
from market import get_market_regime

data_engine = DataEngine()
feature_engine = FeatureEngine()
signal_engine = SignalEngine()
scoring_engine = ScoringEngine()

pipeline = Pipeline(
    data_engine,
    feature_engine,
    signal_engine,
    scoring_engine
)

from data_loader import load_universe

stocks = load_universe()
regime, _, _, _, nifty_return = get_market_regime()

results = pipeline.run(stocks, regime, nifty_return)
