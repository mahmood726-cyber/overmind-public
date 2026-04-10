from __future__ import annotations

ADVANCED_ANALYSIS_PATTERNS: dict[str, tuple[str, ...]] = {
    "meta_analysis": (
        "meta-analysis",
        "meta analysis",
        "meta-regression",
        "meta regression",
        "effect size",
        "heterogeneity",
        "forest plot",
        "pairwise",
    ),
    "network_meta_analysis": (
        "network meta",
        "network-meta",
        "indirect comparison",
        "treatment ranking",
        "league table",
        "sucra",
        "consistency model",
    ),
    "publication_bias_small_study": (
        "publication bias",
        "small-study effect",
        "small study effect",
        "funnel plot",
        "egger",
        "begg",
        "trim and fill",
    ),
    "survival_analysis": (
        "survival",
        "hazard ratio",
        "cox model",
        "cox proportional hazards",
        "kaplan-meier",
        "kaplan meier",
        "time-to-event",
        "time to event",
    ),
    "competing_risks_multistate": (
        "competing risks",
        "competing-risk",
        "fine-gray",
        "fine gray",
        "cause-specific hazard",
        "multi-state",
        "multistate",
    ),
    "bayesian_modeling": (
        "bayesian",
        "bayes",
        "posterior",
        "credible interval",
        "mcmc",
        "hamiltonian monte carlo",
    ),
    "resampling": (
        "bootstrap",
        "jackknife",
        "monte carlo",
        "permutation test",
        "simulation study",
    ),
    "causal_inference": (
        "causal inference",
        "propensity score",
        "inverse probability weighting",
        "instrumental variable",
        "matching estimator",
        "g-method",
    ),
    "diagnostic_accuracy": (
        "diagnostic odds ratio",
        "diagnostic accuracy",
        "sensitivity",
        "specificity",
        "roc curve",
        "auc",
        "likelihood ratio",
        "fagan",
    ),
    "hierarchical_modeling": (
        "hierarchical model",
        "multilevel model",
        "mixed effects",
        "mixed-effects",
        "random effects",
        "frailty model",
        "partial pooling",
    ),
    "calibration_validation": (
        "calibration",
        "discrimination",
        "brier score",
        "c-statistic",
        "c statistic",
        "concordance",
        "hosmer",
    ),
    "missing_data_imputation": (
        "missing data",
        "multiple imputation",
        "imputation",
        "mice",
        "inverse probability censoring",
    ),
    "optimization_numerics": (
        "newton-raphson",
        "newton raphson",
        "gradient descent",
        "optimization",
        "hessian",
        "eigenvalue",
        "positive definite",
        "cholesky",
    ),
    "dose_response_modeling": (
        "dose-response",
        "dose response",
        "restricted cubic spline",
        "fractional polynomial",
        "nonlinear trend",
        "exposure-response",
    ),
    "longitudinal_repeated_measures": (
        "longitudinal",
        "repeated measures",
        "generalized estimating equations",
        " autoregressive ",
        "within-subject",
        "within subject",
        "panel data",
    ),
    "time_series_forecasting": (
        "time series",
        "forecast",
        "arima",
        "seasonal decomposition",
        "state space",
        "changepoint",
    ),
    "measurement_error_reliability": (
        "measurement error",
        "misclassification",
        "reliability",
        "inter-rater",
        "inter rater",
        "intra-class correlation",
        "intraclass correlation",
        "bland-altman",
        "bland altman",
    ),
    "decision_curve_analysis": (
        "decision curve",
        "net benefit",
        "clinical utility",
        "decision analysis",
    ),
    "robust_nonparametric": (
        "nonparametric",
        "rank-based",
        "wilcoxon",
        "mann-whitney",
        "kruskal-wallis",
        "kruskal wallis",
    ),
}

ANALYSIS_SIGNAL_LABELS = {
    "meta_analysis": "meta-analysis",
    "network_meta_analysis": "network meta-analysis",
    "publication_bias_small_study": "publication-bias diagnostics",
    "survival_analysis": "survival analysis",
    "competing_risks_multistate": "competing-risks or multistate modeling",
    "bayesian_modeling": "Bayesian modeling",
    "resampling": "resampling or simulation",
    "causal_inference": "causal inference",
    "diagnostic_accuracy": "diagnostic accuracy",
    "hierarchical_modeling": "hierarchical modeling",
    "calibration_validation": "calibration and validation",
    "missing_data_imputation": "missing data and imputation",
    "optimization_numerics": "numerical optimization",
    "dose_response_modeling": "dose-response modeling",
    "longitudinal_repeated_measures": "longitudinal or repeated-measures analysis",
    "time_series_forecasting": "time-series forecasting",
    "measurement_error_reliability": "measurement error and reliability",
    "decision_curve_analysis": "decision-curve analysis",
    "robust_nonparametric": "robust or nonparametric inference",
}

ANALYSIS_SIGNAL_WEIGHTS = {
    "meta_analysis": 3,
    "network_meta_analysis": 4,
    "publication_bias_small_study": 3,
    "survival_analysis": 3,
    "competing_risks_multistate": 4,
    "bayesian_modeling": 4,
    "resampling": 2,
    "causal_inference": 3,
    "diagnostic_accuracy": 3,
    "hierarchical_modeling": 3,
    "calibration_validation": 2,
    "missing_data_imputation": 2,
    "optimization_numerics": 2,
    "dose_response_modeling": 3,
    "longitudinal_repeated_measures": 3,
    "time_series_forecasting": 3,
    "measurement_error_reliability": 2,
    "decision_curve_analysis": 2,
    "robust_nonparametric": 2,
}

ANALYSIS_FOCUS_BY_SIGNAL = {
    "meta_analysis": ("evidence synthesis",),
    "network_meta_analysis": ("evidence synthesis", "ranking and indirect comparison"),
    "publication_bias_small_study": ("evidence synthesis", "bias diagnostics"),
    "survival_analysis": ("survival and censored outcomes",),
    "competing_risks_multistate": ("survival and censored outcomes", "multistate event modeling"),
    "bayesian_modeling": ("probabilistic inference",),
    "resampling": ("simulation and uncertainty quantification",),
    "causal_inference": ("causal estimation",),
    "diagnostic_accuracy": ("diagnostic performance",),
    "hierarchical_modeling": ("multilevel partial pooling",),
    "calibration_validation": ("prediction validation",),
    "missing_data_imputation": ("missing-data handling",),
    "optimization_numerics": ("numerical optimization and matrix algebra",),
    "dose_response_modeling": ("nonlinear exposure-response modeling",),
    "longitudinal_repeated_measures": ("correlated and longitudinal outcomes",),
    "time_series_forecasting": ("temporal modeling and forecasting",),
    "measurement_error_reliability": ("measurement reliability",),
    "decision_curve_analysis": ("clinical utility and decision analysis",),
    "robust_nonparametric": ("distribution-robust inference",),
}

ANALYSIS_RISKS_BY_SIGNAL = {
    "meta_analysis": ("heterogeneity and effect-size specification",),
    "network_meta_analysis": ("indirect-comparison consistency and ranking stability",),
    "publication_bias_small_study": ("small-study effects and publication bias",),
    "survival_analysis": ("censoring and proportional-hazards assumptions",),
    "competing_risks_multistate": ("competing-risk coding and transition consistency",),
    "bayesian_modeling": ("sampler convergence and prior sensitivity",),
    "resampling": ("stochastic reproducibility and Monte Carlo error",),
    "causal_inference": ("identification assumptions and covariate balance",),
    "diagnostic_accuracy": ("threshold instability and class-imbalance drift",),
    "hierarchical_modeling": ("variance-component shrinkage assumptions",),
    "calibration_validation": ("calibration drift and transportability",),
    "missing_data_imputation": ("missingness mechanism sensitivity",),
    "optimization_numerics": ("optimizer convergence and matrix conditioning",),
    "dose_response_modeling": ("nonlinear functional-form sensitivity",),
    "longitudinal_repeated_measures": ("within-subject correlation structure",),
    "time_series_forecasting": ("temporal leakage and non-stationarity",),
    "measurement_error_reliability": ("measurement error and agreement drift",),
    "decision_curve_analysis": ("net-benefit threshold sensitivity",),
    "robust_nonparametric": ("distributional robustness and tie handling",),
}

ANALYSIS_CHECKS_BY_SIGNAL = {
    "meta_analysis": ("heterogeneity_checks",),
    "network_meta_analysis": ("consistency_checks", "ranking_stability", "heterogeneity_checks"),
    "publication_bias_small_study": ("publication_bias_checks",),
    "survival_analysis": ("censoring_checks",),
    "competing_risks_multistate": ("censoring_checks", "competing_risks_checks"),
    "bayesian_modeling": ("posterior_sanity_checks", "convergence_checks"),
    "resampling": ("stochastic_stability",),
    "causal_inference": ("identification_checks",),
    "diagnostic_accuracy": ("threshold_stability_checks",),
    "hierarchical_modeling": ("variance_component_checks",),
    "calibration_validation": ("calibration_checks",),
    "missing_data_imputation": ("missing_data_checks",),
    "optimization_numerics": ("convergence_checks", "matrix_stability_checks"),
    "dose_response_modeling": ("shape_constraint_checks",),
    "longitudinal_repeated_measures": ("correlation_structure_checks",),
    "time_series_forecasting": ("temporal_backtest_checks",),
    "measurement_error_reliability": ("measurement_error_checks",),
    "decision_curve_analysis": ("decision_curve_checks",),
    "robust_nonparametric": ("distribution_robustness_checks",),
}


def detect_analysis_signals(text: str) -> list[str]:
    lowered = text.lower()
    signals: list[str] = []
    for signal, patterns in ADVANCED_ANALYSIS_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            signals.append(signal)
    return signals


def describe_analysis_signals(signals: list[str]) -> list[str]:
    labels: list[str] = []
    for signal in signals:
        label = ANALYSIS_SIGNAL_LABELS.get(signal, signal.replace("_", " "))
        if label not in labels:
            labels.append(label)
    return labels


def describe_analysis_focus_areas(signals: list[str]) -> list[str]:
    focus_areas: list[str] = []
    for signal in signals:
        for label in ANALYSIS_FOCUS_BY_SIGNAL.get(signal, ()):
            if label not in focus_areas:
                focus_areas.append(label)
    return focus_areas


def describe_analysis_risk_factors(signals: list[str]) -> list[str]:
    factors: list[str] = []
    for signal in signals:
        for label in ANALYSIS_RISKS_BY_SIGNAL.get(signal, ()):
            if label not in factors:
                factors.append(label)
    return factors


def recommended_analysis_checks(
    signals: list[str],
    *,
    score: int,
    has_validation_history: bool = False,
    has_oracle_benchmarks: bool = False,
    has_drift_history: bool = False,
) -> list[str]:
    checks: list[str] = []
    for signal in signals:
        for check in ANALYSIS_CHECKS_BY_SIGNAL.get(signal, ()):
            if check not in checks:
                checks.append(check)
    if score >= 8 and "model_assumption_checks" not in checks:
        checks.append("model_assumption_checks")
    if score >= 10 and (
        has_validation_history or has_oracle_benchmarks or has_drift_history
    ) and "cross_implementation_parity" not in checks:
        checks.append("cross_implementation_parity")
    return checks


def compute_analysis_score(
    signals: list[str],
    *,
    has_validation_history: bool = False,
    has_oracle_benchmarks: bool = False,
    has_drift_history: bool = False,
) -> int:
    score = sum(ANALYSIS_SIGNAL_WEIGHTS.get(signal, 1) for signal in dict.fromkeys(signals))
    if has_validation_history:
        score += 1
    if has_oracle_benchmarks:
        score += 2
    if has_drift_history:
        score += 2
    return min(score, 20)


def analysis_rigor_level(score: int) -> str:
    if score >= 10:
        return "extreme"
    if score >= 6:
        return "high"
    if score >= 3:
        return "moderate"
    if score > 0:
        return "light"
    return "none"
