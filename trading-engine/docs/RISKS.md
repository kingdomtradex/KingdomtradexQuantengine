# Risk Disclosures and Limitations

## ⚠️ Critical Risk Warning

This software implements an **aggressive trading strategy** with elevated leverage (up to 10.0x gross). The 2.5% daily net return target is an **operational objective, not a guarantee**. Past performance does not guarantee future results.

## 1. Capacity Constraints

### Market Impact Saturation

The strategy saturates at approximately **$15M AUM** due to market impact. Beyond this threshold:

- Own flow moves the market
- Alpha compresses non-linearly
- Liquidation risk increases through feedback loops

**Note:** This capacity estimate is derived from backtests assuming zero footprint at small scale. Actual capacity may be lower due to unmodelled venue-level execution constraints.

## 2. Leverage and Liquidation Risk

### Margin Liquidation Probability

Under the 10.0x leverage regime, the probability of at least one margin-liquidation event over a 3-year horizon is approximately **68%** (derived from VaR backtesting).

A single gap move that bypasses the circuit breaker can force liquidation at severely adverse prices. During flash crashes, liquidity evaporates precisely when de-leveraging is most urgent.

### Survivorship Trade-off

The 2.5% daily target requires near-perfect execution:
- Tight latency (<1ms RTT)
- Accurate regime classification
- Reliable collateral optimization

All three must hold simultaneously. The margin for error is thin.

## 3. Regulatory Risk

The fragmented nature of global crypto and equity regulation poses constant threats:
- Venue-level shutdowns
- High-leverage strategies attract heightened prime-broker scrutiny
- Changing margin requirements
- Potential position limits

## 4. Alpha Decay

Statistical regularities exploited by this system are **equilibrium rents** that will compress as competitors deploy similar architectures. Alpha decay is a structural certainty.

Mitigation strategies:
- Continuous online training
- Weekly hyperparameter optimization
- Multi-agent ensemble diversification

However, no edge is permanent.

## 5. Model Risk

### HMM Regime Classification

- Assumes Markov property (may not hold)
- Parameters estimated from historical data (non-stationary)
- Re-estimation frequency (daily) may miss rapid regime transitions

### TCN Forecasting

- Model weights decay over time
- Subject to overfitting on historical patterns
- Performance degrades in unseen regimes

### PPO Meta-Learner

- Reinforcement learning introduces additional variance
- Policy updates may be destabilizing during regime transitions
- Requires careful tuning of clipping parameter ε

## 6. Execution Risk

### Latency Asymmetry

Co-located participants observe order book updates in hundreds of nanoseconds. Remote participants face microsecond-to-millisecond delays, creating chronic adverse selection.

### Slippage and Fees

At 10.0x leverage and high turnover across 350+ instruments:
- Execution friction is ~0.7% daily (~22% of gross revenue)
- Any degradation in execution quality erodes net target directly
- Slippage control is a risk constraint, not a cost externality

## 7. Circuit Breaker Limitations

The hard-stop circuit breaker at -2.5% daily drawdown:
- May be bypassed during gap moves
- Cannot prevent losses between monitoring intervals
- Liquidation into thin liquidity may exceed expected slippage

## 8. Collateral Optimization Risk

Real-time collateral optimization is essential for 10.0x leverage:
- Cross-venue margin netting assumptions may fail
- Intra-session reallocation may be blocked during stress
- Rehypothecation delays at venues can trigger cascading liquidations

## 9. Backtest Limitations

### Key Assumptions

| Asset Class | Fee (bps) | Slippage (bps) |
|-------------|-----------|----------------|
| Crypto      | 2.0       | 1.0            |
| Equities/ETFs | 0.5    | Included       |
| Futures     | 0.3       | Included       |

### Caveats

- Backtests assume zero market impact at small scale
- Historical data may not reflect future microstructure
- Transaction costs may increase in competitive environments
- Gap risk not fully captured in tick-level backtests

## 10. Operational Risks

- FPGA firmware bugs
- Network partitioning
- Exchange API changes
- Data feed interruptions
- Clock synchronization failures

## Disclaimer

**THIS SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND.**

This software is for educational and research purposes only. It is not intended for production trading without extensive validation, regulatory compliance review, and appropriate risk controls.

The authors make no representations or warranties regarding:
- Accuracy of models or predictions
- Achievement of return targets
- Prevention of losses
- Suitability for any particular purpose

**Users assume all risks associated with use of this software.**
