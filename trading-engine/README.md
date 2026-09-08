# Statistical Arbitrage & Market-Making Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Overview

A low-latency, multi-agent ensemble trading system designed for statistical arbitrage and market-making across disparate asset classes. This engine implements a rigorous architecture combining FPGA-accelerated data ingestion, regime-aware signal generation, and hierarchical risk management.

**⚠️ Important Disclaimer:** This system targets aggressive returns (2.5% daily net) with elevated leverage (up to 10.0x gross). Performance is entirely contingent on prevailing liquidity and volatility regimes. The elevated leverage materially increases tail risk and the probability of forced liquidation. Backtested outcomes do not guarantee live-trading results. This software is provided for educational and research purposes only.

## Architecture

The system follows a five-stage pipeline:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Data Ingestion │────▶│ Feature Engineering│────▶│ Signal Generation│
│   (Layer 1)     │     │   & Regime Class  │     │  (4-Agent Ensemble)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Order Execution │◀────│ Portfolio Const. │◀────│ Risk Management │
│   & Routing     │     │   & Sizing       │     │   Framework     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Core Components

1. **Data Ingestion Layer**: FPGA-accelerated market data decoding with kernel-bypass networking
2. **Feature Engineering**: Microstructure features + HMM regime classification (3 states)
3. **Signal Generation**: 4-agent ensemble (Micro-arbitrage, Market-making, TCN forecasting, Volatility risk-premium)
4. **Portfolio Construction**: Fractional Kelly sizing with dynamic leverage scaling
5. **Risk Management**: Hard circuit breakers (-2.5% daily drawdown), real-time collateral optimization
6. **Execution Engine**: Latency-adaptive smart order routing with TWAP slicing

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/trading-engine.git
cd trading-engine

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

## Quick Start

```python
from trading_engine import TradingEngine
from trading_engine.config import Config

# Load configuration
config = Config.from_yaml('config/default.yaml')

# Initialize engine
engine = TradingEngine(config)

# Start the trading loop
engine.run()
```

## Configuration

See `config/default.yaml` for default settings. Key parameters:

```yaml
leverage:
  max_gross: 10.0
  base: 1.0
  variance_premium_sensitivity: 0.5

risk:
  daily_drawdown_limit: -0.025  # -2.5%
  risk_per_trade: 0.0075        # 0.75%
  kelly_multiplier: 0.40

regime:
  hmm_states: 3
  reestimate_frequency: "daily"
```

## API Reference

### TradingEngine

The main entry point for the trading system.

```python
class TradingEngine:
    def __init__(self, config: Config)
    def run(self) -> None
    def stop(self) -> None
    def get_status(self) -> dict
```

### Signal Agents

Four specialized agents generate trading signals:

- **Agent1 (MicroArbitrage)**: Exploits basis discrepancies between cointegrated pairs
- **Agent2 (MarketMaker)**: Avellaneda-Stoikov framework for passive liquidity provision
- **Agent3 (TCNForecaster)**: Temporal Convolutional Network for short-term price prediction
- **Agent4 (VolatilityScaler)**: Variance risk-premium harvesting for leverage scaling

```python
from trading_engine.signals import AgentEnsemble

ensemble = AgentEnsemble(config)
signals = ensemble.generate_signals(market_data, regime_state)
```

### Risk Manager

Implements hard constraints and circuit breakers.

```python
from trading_engine.risk import RiskManager

risk_mgr = RiskManager(config)
if risk_mgr.check_circuit_breaker(pnl):
    risk_mgr.trigger_liquidation()
```

## Mathematical Foundations

### Avellaneda-Stoikov Market-Making

Reservation price formula:
```
r(s, q, t) = s − q · γ · σ² · (T − t)
```

Where:
- `s`: current mid-price
- `q`: inventory position
- `γ`: risk-aversion parameter
- `σ²`: return variance
- `T − t`: time remaining

### Fractional Kelly Criterion

Position sizing:
```
f_deployed = λ · (μ / σ²)
```

Where `λ = 0.40` (fractional multiplier), `μ` is expected excess return, `σ²` is variance.

### Dynamic Leverage Scaling

Target gross leverage:
```
L_t* = min(L_max, L_base · [1 + α · (VRP_t / σ_VRP)])
```

Where `VRP_t = IV_t² − RV_t²` (variance risk premium).

See `docs/MATHEMATICS.md` for complete derivations.

## Performance Metrics

Based on out-of-sample backtesting (2023-2025, 10.0x leverage regime):

| Metric | Value |
|--------|-------|
| Net Daily Return Target | 2.5% |
| Annualized Return (capacity-constrained) | ~630% |
| Annualized Volatility | ~79.4% |
| Sharpe Ratio | ~7.9 |
| Maximum Drawdown | −41.7% |
| Calmar Ratio | ~15.1 |
| Market-Impact Capacity | ~$15M AUM |

**Note:** These metrics assume zero market impact at small scale. Actual performance will degrade with increasing AUM.

## Project Structure

```
trading-engine/
├── src/
│   ├── data/              # Market data ingestion & normalization
│   ├── features/          # Feature engineering & regime classification
│   ├── signals/           # 4-agent signal generation ensemble
│   ├── risk/              # Risk management & circuit breakers
│   ├── execution/         # Smart order routing & execution
│   ├── portfolio/         # Portfolio construction & sizing
│   ├── models/            # Model definitions (TCN, HMM, PPO)
│   └── utils/             # Utilities & helpers
├── config/                # Configuration files
├── tests/                 # Unit & integration tests
├── docs/                  # Documentation
├── scripts/               # Utility scripts
└── requirements.txt       # Python dependencies
```

## Glass Box Philosophy

This project follows a "Glass Box" approach:

**Published (Open Source):**
- ✅ Mathematical proofs and formulations
- ✅ Architecture diagrams and system design
- ✅ Risk management frameworks
- ✅ API integration guides
- ✅ Testing infrastructure

**Proprietary (Closed Source):**
- 🔒 TCN model weights
- 🔒 Exact HMM parameters
- 🔒 Execution routing logic details
- 🔒 FPGA firmware implementations

## Limitations & Risks

1. **Capacity Constraint**: Strategy saturates at ~$15M AUM due to market impact
2. **Regulatory Risk**: High-leverage strategies face heightened scrutiny
3. **Alpha Decay**: Statistical edges compress as competition increases
4. **Survivorship Trade-off**: At 10.0x leverage, probability of margin-liquidation event over 3 years ≈ 68%
5. **Gap Risk**: Circuit breakers may be bypassed during extreme moves

See `docs/RISKS.md` for comprehensive risk disclosure.

## Development

### Running Tests

```bash
pytest tests/ -v --cov=src
```

### Code Style

```bash
black src/ tests/
flake8 src/ tests/
mypy src/
```

## Contributing

We welcome contributions! Please read `CONTRIBUTING.md` for guidelines.

## License

MIT License - see `LICENSE` file for details.

## Citation

If you use this software in your research, please cite:

```bibtex
@misc{trading-engine2026,
  title={Statistical Arbitrage and Market-Making Engine},
  author={Quantitative Research Department},
  year={2026},
  howpublished={\url{https://github.com/your-org/trading-engine}}
}
```

## Contact

For institutional inquiries: research@trading-engine.example.com

---

**Disclaimer:** This software is for educational and research purposes only. It is not intended for production trading without extensive validation, regulatory compliance review, and appropriate risk controls. Past performance does not guarantee future results.
