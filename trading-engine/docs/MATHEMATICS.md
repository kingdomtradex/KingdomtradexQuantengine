# Mathematical Foundations of the Trading Engine

This document provides the complete mathematical formulations governing the core algorithmic components of the statistical arbitrage and market-making system.

## 1. Avellaneda-Stoikov Market-Making Formulation

### 1.1 Reservation Price

The reservation price serves as the anchor for the market-making agent's quotes:

```
r(s, q, t) = s - q * gamma * sigma^2 * (T - t)
```

Where:
- `s`: Current mid-price
- `q`: Current inventory position (positive = long)
- `gamma`: Risk aversion parameter (default: 0.1)
- `sigma^2`: Variance of the asset's returns
- `T`: Terminal time of trading horizon
- `t`: Current time

### 1.2 Optimal Spread

The optimal half-spread is calculated to balance execution probability against adverse selection:

```
delta* = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / kappa)
```

Where `kappa` represents the intensity of order arrival at the quoted spread.

### 1.3 Value Function

The HJB equation governing the market maker's value function:

```
partial_t v + max_delta [ lambda(delta) * (v(t, s, q-1, delta) - v(t, s, q) ) ] 
           + max_epsilon [ lambda(epsilon) * (v(t, s, q+1, -epsilon) - v(t, s, q) ) ]
           + (1/2) * sigma^2 * partial_ss v = 0
```

---

## 2. Proximal Policy Optimization (PPO) Objective

### 2.1 Clipped Surrogate Objective

The meta-learner uses PPO to update policy parameters with the clipped objective:

```
L(theta) = E_t [ min( r_t(theta) * A_t, clip(r_t(theta), 1 - epsilon, 1 + epsilon) * A_t ) ]
```

Where:
- `r_t(theta) = pi_theta(a_t | s_t) / pi_theta_old(a_t | s_t)`: Probability ratio
- `A_t`: Estimated advantage function
- `epsilon`: Clipping hyperparameter (typically 0.2)

### 2.2 Advantage Estimation

Generalized Advantage Estimation (GAE):

```
A_t = delta_t + (gamma * lambda) * delta_{t+1} + ... + (gamma * lambda)^{T-t-1} * delta_{T-1}
```

Where:
- `delta_t = r_t + gamma * V(s_{t+1}) - V(s_t)`: TD residual
- `gamma`: Discount factor
- `lambda`: GAE parameter for bias-variance tradeoff

### 2.3 State and Action Spaces

**State Space S_t:**
- Trailing 200-trade Sharpe ratios for Agents 1, 2, 3, 4
- Posterior probabilities of three HMM regime states
- Current variance risk premium
- Normalized inventory vector across asset classes
- Cyclical time-of-day embeddings (sin/cos transformation)

**Action Space A_t:**
- Continuous 4-dimensional simplex
- Output: portfolio weights [w_1, w_2, w_3, w_4]
- Constraint: sum(w_i) = 1, w_i >= 0

---

## 3. Fractional Kelly Criterion

### 3.1 Full Kelly Fraction

The optimal fraction for maximizing logarithmic utility:

```
f* = mu / sigma^2
```

Where:
- `mu`: Expected excess return
- `sigma^2`: Variance of returns

### 3.2 Fractional Kelly

To account for parameter estimation error, we apply a fractional multiplier:

```
f_deployed = lambda * f* = lambda * (mu / sigma^2)
```

Where `lambda = 0.40` (pre-commitment locked per technical specification).

### 3.3 Risk-Per-Trade Cap

Position size is further constrained:

```
|position| <= (risk_per_trade * equity) / sigma
```

With `risk_per_trade = 0.0075` (0.75% hard limit).

---

## 4. Dynamic Leverage Scaling via Variance Risk Premium

### 4.1 Variance Risk Premium Definition

```
VRP_t = IV_t^2 - RV_t^2
```

Where:
- `IV_t`: Implied volatility (from CBOE VIX and options surfaces)
- `RV_t`: Realized volatility (from Parkinson and EWMA estimators)

### 4.2 Target Gross Leverage

```
L_t* = min( L_max, L_base * [1 + alpha * (VRP_t / sigma_VRP)] )
```

Where:
- `L_max = 10.0`: Maximum leverage ceiling
- `L_base = 1.0`: Baseline leverage
- `alpha = 0.5`: Sensitivity coefficient (vrp_sensitivity)
- `sigma_VRP`: Trailing standard deviation of VRP

### 4.3 Regime Gating

Final leverage is gated by HMM regime state:

```
L_final = L_t* * exposure_cap(regime_state)
```

Where:
- State 0 (Low-Vol): exposure_cap = 1.0
- State 1 (High-Vol): exposure_cap = 0.5
- State 2 (Fractured): exposure_cap = 0.2

---

## 5. Hidden Markov Model for Regime Classification

### 5.1 Model Specification

Three-state HMM with Gaussian emissions:

```
P(z_t = j | z_{t-1} = i) = A_{ij}  (transition matrix)
P(x_t | z_t = j) = N(x_t; mu_j, Sigma_j)  (emission distribution)
```

### 5.2 Forward Algorithm

```
alpha_t(j) = [sum_i alpha_{t-1}(i) * A_{ij}] * P(x_t | z_t = j)
```

### 5.3 Posterior State Probability

```
gamma_t(j) = alpha_t(j) / sum_k alpha_t(k)
```

The posterior `gamma_t` acts as a hard gate for risk limits.

---

## 6. Ledoit-Wolf Shrinkage Estimator

### 6.1 Sample Covariance

```
S = (1/T) * sum_{t=1}^{T} (r_t - r_bar)(r_t - r_bar)'
```

### 6.2 Shrinkage Target

```
F = phi * I_n
```

Where `phi = (1/n) * trace(S)` is the average sample variance.

### 6.3 Optimal Shrinkage Intensity

```
kappa = ((1/T) * sum_{t=1}^{T} ||X_t X_t' - S||_F^2) / ||S - F||_F^2
```

### 6.4 Shrunk Estimator

```
Sigma_shrunk = kappa * F + (1 - kappa) * S
```

Typical shrinkage intensity: 0.2 for this application.

---

## 7. Unit-of-Risk Normalization

### 7.1 Definition

Unit-of-Risk enables cross-asset comparability:

```
UOR = notional / sigma_trailing
```

Where `sigma_trailing` is the standard deviation of the instrument's trailing return distribution.

### 7.2 Portfolio Aggregation

Positions across asset classes are aggregated in UOR terms:

```
Total_UOR_Exposure = sum_i |position_i| / sigma_i
```

This allows the risk engine to treat crude oil futures, equity ETFs, and Bitcoin perpetual swaps on a mathematically comparable basis.

---

## 8. Parkinson Volatility Estimator

### 8.1 Single-Day Estimate

```
sigma_P^2 = (1 / (4 * ln(2))) * (ln(H/L))^2
```

Where `H` and `L` are the high and low prices over the period.

### 8.2 Multi-Day Average

```
sigma_RV^2 = (1/T) * sum_{t=1}^{T} sigma_P,t^2
```

---

## 9. Circuit Breaker Protocol

### 9.1 Trigger Condition

```
trigger = (daily_pnl / start_equity) < drawdown_threshold
```

Where `drawdown_threshold = -0.025` (-2.5%).

### 9.2 Pre-emptive De-leveraging

```
delever_trigger = collateral_utilization > 0.80
```

### 9.3 Liquidation Orders

Upon trigger:
1. Cease all order generation
2. Liquidate to delta-neutral: `position_i = 0` for all `i`
3. Enter Observation Only state until next settlement

---

## 10. TWAP Execution with Stochastic Noise

### 10.1 Base Slice Size

```
q_base = Q_total / N_slices
```

### 10.2 Noisy Slice

```
q_i = q_base * (1 + epsilon_i), where epsilon_i ~ N(0, sigma_noise^2)
```

Where `sigma_noise = 0.1` (10% standard deviation).

### 10.3 Timing Jitter

Slice timing also receives stochastic perturbation to reduce predictability.

---

## References

1. Avellaneda, M., & Stoikov, S. (2008). High-Frequency Trading in a Limit Order Book. Quantitative Finance.
2. Schulman, J., et al. (2017). Proximal Policy Optimization Algorithms. arXiv:1707.06347.
3. Kelly, J. L. (1956). A New Interpretation of Information Rate. Bell System Technical Journal.
4. Ledoit, O., & Wolf, M. (2004). A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices. Journal of Multivariate Analysis.
5. Parkinson, M. (1980). The Extreme Value Method for Estimating the Variance of the Rate of Return. Journal of Business.
6. Carr, P., & Wu, L. (2009). Variance Risk Premiums. Review of Financial Studies.
