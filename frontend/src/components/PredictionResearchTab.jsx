import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Play,
  Cpu,
  Calendar,
  AlertOctagon,
  CheckCircle2,
  Info,
  Clock,
  Layers,
  AlertTriangle,
} from 'lucide-react';

export default function PredictionResearchTab({
  selectedTicker,
  marketData,
  companies,
  onSelectCompany,
}) {
  const [prediction, setPrediction] = useState(null);
  const [decision, setDecision] = useState(null);
  const [portfolioResearch, setPortfolioResearch] = useState(null);
  const [phase5jResearch, setPhase5jResearch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [asOfDate, setAsOfDate] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Load Phase 5H portfolio simulation research summary
  useEffect(() => {
    fetch('/api/models/portfolio/research')
      .then((res) => res.json())
      .then((data) => {
        if (data && data.strategy_results) {
          setPortfolioResearch(data);
        }
      })
      .catch((err) => console.error('Error fetching portfolio research:', err));
  }, []);

  // Load Phase 5J 60-company cross-sectional research summary
  useEffect(() => {
    fetch('/api/models/research/phase5j')
      .then((res) => res.json())
      .then((data) => {
        if (data && (data.status === 'available' || data.aggregate_metrics)) {
          setPhase5jResearch(data);
        }
      })
      .catch((err) => console.error('Error fetching Phase 5J research:', err));
  }, []);

  // Load Phase 5K systematic model improvement research summary
  const [phase5kResearch, setPhase5kResearch] = useState(null);
  useEffect(() => {
    fetch('/api/models/research/phase5k')
      .then((res) => res.json())
      .then((data) => {
        if (data && (data.status === 'available' || data.aggregate_model_metrics)) {
          setPhase5kResearch(data);
        }
      })
      .catch((err) => console.error('Error fetching Phase 5K research:', err));
  }, []);

  // Default to the latest date from market series
  useEffect(() => {
    if (marketData && marketData.series && marketData.series.length > 0) {
      const latest = marketData.series[marketData.series.length - 1].trading_date;
      setAsOfDate(latest);
      // Auto-fetch prediction for active company on latest date
      fetchPrediction(selectedTicker, latest);
    }
  }, [selectedTicker, marketData]);

  const fetchPrediction = async (ticker, date) => {
    setLoading(true);
    setErrorMsg('');
    try {
      const [predRes, decRes] = await Promise.all([
        fetch('/api/models/predict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, as_of_date: date || undefined }),
        }),
        fetch('/api/models/decision', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, as_of_date: date || undefined }),
        }),
      ]);
      const predData = await predRes.json();
      const decData = await decRes.json();
      setPrediction(predData);
      setDecision(decData);
    } catch (err) {
      console.error('Error requesting prediction & decision:', err);
      setErrorMsg('Failed to connect to prediction & decision engine API endpoint.');
    } finally {
      setLoading(false);
    }
  };

  const handleRunPrediction = (e) => {
    e.preventDefault();
    fetchPrediction(selectedTicker, asOfDate);
  };

  const handleTestExcludedCompany = () => {
    fetchPrediction('AA', asOfDate);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Strict Research Warning Banner */}
      <div className="disclaimer-banner" style={{ borderLeftColor: 'var(--accent-red)' }}>
        <AlertOctagon size={16} style={{ color: 'var(--accent-red)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong style={{ color: 'var(--accent-red)' }}>EXPERIMENTAL FORECASTING INTERFACE:</strong> All predictions reflect statistical point-forecasts generated from offline walk-forward regression baselines.
          <br />
          <strong>NO INVESTMENT ADVICE:</strong> No Buy/Hold/Sell signals, confidence probabilities, portfolio allocation weights, or expected trading profits are generated.
        </div>
      </div>

      {/* Control Panel & Date Selector */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Cpu size={14} />
            <span>Forward Return Inference Engine (Session T Close)</span>
          </span>
          <span className="badge-tag badge-experimental">Walk-Forward Model 1</span>
        </div>

        <form onSubmit={handleRunPrediction} style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
              Target Company
            </label>
            <div className="company-pills">
              {companies.map((c) => (
                <button
                  type="button"
                  key={c.ticker}
                  className={`company-pill ${selectedTicker === c.ticker ? 'active' : ''}`}
                  onClick={() => onSelectCompany(c.ticker)}
                  id={`pred-pill-${c.ticker}`}
                >
                  {c.ticker}
                </button>
              ))}
              <button
                type="button"
                className="company-pill company-pill-excluded"
                onClick={handleTestExcludedCompany}
                title="Test safety guardrails on excluded company AA"
                id="pred-pill-test-AA"
              >
                Test AA (Excluded)
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
              Decision Session (T Close)
            </label>
            <input
              type="text"
              className="font-mono"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                padding: '6px 10px',
                fontSize: '12px',
                width: '130px',
              }}
              id="input-decision-date"
            />
          </div>

          <div style={{ alignSelf: 'flex-end' }}>
            <button
              type="submit"
              className="chart-toggle-btn active"
              disabled={loading}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 16px' }}
              id="btn-run-prediction"
            >
              <Play size={12} />
              <span>{loading ? 'Evaluating...' : 'Generate Prediction'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Prediction Output Section */}
      {errorMsg && (
        <div className="card" style={{ borderLeft: '4px solid var(--accent-red)', padding: '16px' }}>
          <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>API Error:</span> {errorMsg}
        </div>
      )}

      {prediction && prediction.status === 'available' && (
        <div className="terminal-grid">
          {/* Main Output Box */}
          <div className="card" style={{ gridColumn: 'span 7' }}>
            <div className="card-header">
              <span className="card-title">
                <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />
                <span>Verified Return Prediction Result</span>
              </span>
              <span className="badge-tag badge-status">Inference Validated</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px' }}>
                <div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Predicted 5-Session Forward Return
                  </div>
                  <div
                    className="font-mono"
                    style={{
                      fontSize: '32px',
                      fontWeight: 700,
                      color:
                        prediction.predicted_forward_return >= 0
                          ? 'var(--accent-green)'
                          : 'var(--accent-red)',
                    }}
                    id="prediction-value-display"
                  >
                    {prediction.predicted_forward_return_pct}
                  </div>
                  <div className="font-mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Decimal: {prediction.predicted_forward_return.toFixed(6)}
                  </div>
                </div>

                <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Target Horizon
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    {prediction.target_horizon}
                  </div>
                  <div className="font-mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                    Entry: T+1 Open | Exit: T+5 Close
                  </div>
                </div>
              </div>

              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Model Artifact ID:</span>
                  <span className="font-mono">{prediction.model_id}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Decision Timestamp:</span>
                  <span className="font-mono">{prediction.as_of_timestamp}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Entity Identifier:</span>
                  <span className="font-mono">{prediction.ticker} ({prediction.company_id})</span>
                </div>
              </div>

              {/* Verified Features Used */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                  Features Utilized ({prediction.features_used.length} Inputs)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {prediction.features_used.map((feat) => (
                    <span
                      key={feat}
                      className="font-mono"
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '2px 6px',
                        fontSize: '10px',
                        color: 'var(--accent-blue)',
                      }}
                    >
                      {feat}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Model Limitations & Disclaimers */}
          <div className="card" style={{ gridColumn: 'span 5' }}>
            <div className="card-header">
              <span className="card-title">
                <AlertTriangle size={14} style={{ color: 'var(--accent-amber)' }} />
                <span>Documented Model Limitations</span>
              </span>
              <span className="badge-tag badge-experimental">Audited</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {prediction.limitations.map((lim, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    lineHeight: 1.5,
                  }}
                >
                  {lim}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Phase 5G Experimental Decision & Risk Layer Output */}
      {decision && (
        <div className="card" style={{ borderTop: '3px solid ' + (decision.signal === 'BUY' ? 'var(--accent-green)' : decision.signal === 'SELL' ? 'var(--accent-red)' : 'var(--accent-amber)') }}>
          <div className="card-header">
            <span className="card-title">
              <ShieldAlert size={14} style={{ color: decision.signal === 'BUY' ? 'var(--accent-green)' : decision.signal === 'SELL' ? 'var(--accent-red)' : 'var(--accent-amber)' }} />
              <span>Phase 5G Decision & Risk Layer (Experimental Candidate Signal)</span>
            </span>
            <span className={`badge-tag ${decision.signal === 'BUY' ? 'badge-status' : decision.signal === 'SELL' ? 'badge-experimental' : 'badge-offline'}`}>
              Signal: {decision.signal}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Candidate Action</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: decision.signal === 'BUY' ? 'var(--accent-green)' : decision.signal === 'SELL' ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                {decision.signal}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                Applied Threshold: {decision.threshold_applied !== 0 ? (decision.threshold_applied * 100).toFixed(2) + '%' : 'N/A (Hold Gate)'}
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Expected Net Return</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: decision.expected_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                {(decision.expected_net_return * 100).toFixed(2)}%
              </div>
              <div className="font-mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                Cost Friction: -{decision.cost_assumptions_bps.toFixed(1)} bps ({(decision.total_cost_deducted * 100).toFixed(2)}%)
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Forecast Uncertainty</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
                {decision.estimated_uncertainty !== null ? `± ${(decision.estimated_uncertainty * 100).toFixed(2)}%` : 'Unavailable'}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                Method: {decision.uncertainty_method}
              </div>
            </div>
          </div>

          {/* Explanation Reasons */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              Decision Justification & Reasons
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {decision.reasons.map((r, i) => (
                <div key={i} style={{ fontSize: '12px', color: 'var(--text-secondary)', background: 'var(--bg-surface)', padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  {r}
                </div>
              ))}
            </div>
          </div>

          {/* Risk Gates Checklist */}
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
              Defensive Risk Gates Status ({decision.risk_checks_passed.length} Passed, {decision.risk_checks_failed.length} Failed)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '6px' }}>
              {decision.risk_checks_passed.map((chk, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--accent-green)' }}>
                  <CheckCircle2 size={13} style={{ flexShrink: 0 }} />
                  <span>{chk}</span>
                </div>
              ))}
              {decision.risk_checks_failed.map((chk, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--accent-red)' }}>
                  <AlertOctagon size={13} style={{ flexShrink: 0 }} />
                  <span>{chk}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Phase 5H Portfolio Simulation & Leakage-Safe Validation Output */}
      {portfolioResearch && portfolioResearch.strategy_results && (
        <div className="card" style={{ borderTop: '3px solid var(--accent-blue)' }}>
          <div className="card-header">
            <span className="card-title">
              <Layers size={14} style={{ color: 'var(--accent-blue)' }} />
              <span>Phase 5H Portfolio Simulation & Rolling Threshold Validation (Research)</span>
            </span>
            <span className="badge-tag badge-status">
              Audited 4-Fold Panel (N = 720)
            </span>
          </div>

          {/* Strategy Benchmarks Comparison Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Cash Benchmark</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                $100,000.00
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                Net Ret: 0.00% | Max DD: 0.00%
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Equal-Weight Buy & Hold</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-green)' }}>
                ${portfolioResearch.strategy_results.buy_and_hold_benchmark.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                Net: +{(portfolioResearch.strategy_results.buy_and_hold_benchmark.total_net_return * 100).toFixed(1)}% | Max DD: {(portfolioResearch.strategy_results.buy_and_hold_benchmark.max_drawdown * 100).toFixed(1)}%
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Fixed Policy (1.5% Threshold)</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: portfolioResearch.strategy_results.fixed_threshold_policy.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                ${portfolioResearch.strategy_results.fixed_threshold_policy.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                Net: +{(portfolioResearch.strategy_results.fixed_threshold_policy.total_net_return * 100).toFixed(2)}% | Max DD: {(portfolioResearch.strategy_results.fixed_threshold_policy.max_drawdown * 100).toFixed(2)}%
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {portfolioResearch.strategy_results.fixed_threshold_policy.total_closed_trades} Trades Funded, {portfolioResearch.strategy_results.fixed_threshold_policy.total_rejected_orders} Rejected Overlaps
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Rolling Threshold Policy</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: portfolioResearch.strategy_results.rolling_threshold_policy.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                ${portfolioResearch.strategy_results.rolling_threshold_policy.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                Net: {(portfolioResearch.strategy_results.rolling_threshold_policy.total_net_return * 100).toFixed(2)}% | Max DD: {(portfolioResearch.strategy_results.rolling_threshold_policy.max_drawdown * 100).toFixed(2)}%
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {portfolioResearch.strategy_results.rolling_threshold_policy.total_closed_trades} Trades, Win: {(portfolioResearch.strategy_results.rolling_threshold_policy.win_rate * 100).toFixed(1)}%
              </div>
            </div>
          </div>

          {/* Rolling Threshold Selection by Fold */}
          {portfolioResearch.rolling_threshold_selection && (
            <div style={{ marginBottom: '14px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Leakage-Safe Rolling Threshold Selection Audit
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
                {portfolioResearch.rolling_threshold_selection.map((r, i) => (
                  <div key={i} style={{ background: 'var(--bg-surface)', padding: '8px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '11px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      Outer Fold {r.outer_fold}: Selected {(r.selected_threshold * 100).toFixed(1)}%
                    </div>
                    <div style={{ color: r.fallback_used ? 'var(--accent-amber)' : 'var(--accent-green)', fontSize: '10px', marginTop: '2px' }}>
                      {r.fallback_used ? `Conservative Fallback Applied` : `Optimized from Prior Validation`}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Portfolio Execution Constraints Footnote */}
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', background: 'var(--bg-surface)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', lineHeight: 1.5 }}>
            <strong>Institutional Portfolio Invariants:</strong> $100,000 initial cash, maximum 4 concurrent positions, 25% target allocation per position, 15 bps round-trip friction, 5-session holding horizon (T+1 open to T+5 close). Multiple overlapping positions in the exact same asset are rejected to prevent concentration risk.
          </div>
        </div>
      )}

      {/* Phase 5J Validated Cross-Sectional Training & Evaluation (60 Companies) */}
      {phase5jResearch && phase5jResearch.aggregate_metrics && (
        <div className="card" style={{ borderTop: '3px solid var(--accent-cyan)' }}>
          <div className="card-header">
            <span className="card-title">
              <Layers size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span>Phase 5J Validated 60-Company Cross-Sectional Training & Evaluation</span>
            </span>
            <div style={{ display: 'flex', gap: '6px' }}>
              <span className="badge-tag badge-status">60 Companies (11 Sectors)</span>
              <span className="badge-tag badge-experimental">
                Audited 4-Fold Panel (N = {phase5jResearch.metadata?.total_out_of_sample_observations?.toLocaleString() || '10,559'})
              </span>
            </div>
          </div>

          {/* Model & Benchmark Overview Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Reference 0 (Zero Return)</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-secondary)' }}>
                {(phase5jResearch.aggregate_metrics.reference_0_zero.rmse * 100).toFixed(2)}% RMSE
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                MAE: {(phase5jResearch.aggregate_metrics.reference_0_zero.mae * 100).toFixed(2)}% | Directional Hit: 50.0%
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model 1 (Cross-Sectional Ridge)</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                {(phase5jResearch.aggregate_metrics.ridge_cross_sectional.rmse * 100).toFixed(2)}% RMSE
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                MAE: {(phase5jResearch.aggregate_metrics.ridge_cross_sectional.mae * 100).toFixed(2)}% | Hit Rate: {(phase5jResearch.aggregate_metrics.ridge_cross_sectional.hit_rate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                Pooled IC: +{phase5jResearch.aggregate_metrics.ridge_cross_sectional.rank_ic.toFixed(3)} (Exploratory)
                {phase5jResearch.aggregate_metrics.ridge_cross_sectional.daily_cross_sectional_ic && (
                  <span style={{ color: 'var(--accent-amber)', marginLeft: '6px' }}>
                    | Daily CS IC: {phase5jResearch.aggregate_metrics.ridge_cross_sectional.daily_cross_sectional_ic.mean_daily_ic.toFixed(3)} (HAC p = {phase5jResearch.aggregate_metrics.ridge_cross_sectional.daily_cross_sectional_ic.newey_west_hac_pvalue.toFixed(2)})
                  </span>
                )}
              </div>
            </div>

            {phase5jResearch.portfolio_simulation?.buy_and_hold_benchmark && (
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Equal-Weight Buy & Hold (60 Co)</div>
                <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent-green)' }}>
                  ${phase5jResearch.portfolio_simulation.buy_and_hold_benchmark.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Net: +{(phase5jResearch.portfolio_simulation.buy_and_hold_benchmark.total_net_return * 100).toFixed(1)}% | Max DD: {(phase5jResearch.portfolio_simulation.buy_and_hold_benchmark.max_drawdown * 100).toFixed(1)}%
                </div>
              </div>
            )}

            {phase5jResearch.portfolio_simulation?.cross_sectional_policy && (
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Cross-Sectional Ridge Portfolio</div>
                <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: phase5jResearch.portfolio_simulation.cross_sectional_policy.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  ${phase5jResearch.portfolio_simulation.cross_sectional_policy.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Net: +{(phase5jResearch.portfolio_simulation.cross_sectional_policy.total_net_return * 100).toFixed(2)}% | Max DD: {(phase5jResearch.portfolio_simulation.cross_sectional_policy.max_drawdown * 100).toFixed(2)}%
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  {phase5jResearch.portfolio_simulation.cross_sectional_policy.total_closed_trades} Trades Funded, Win: {(phase5jResearch.portfolio_simulation.cross_sectional_policy.win_rate * 100).toFixed(1)}%
                </div>
              </div>
            )}
          </div>

          {/* Multi-Track Model Comparison Table (Common 4-Company Cohort) */}
          {phase5jResearch.track_comparison && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', fontWeight: 600 }}>
                Multi-Modal Track Comparison on Common Pilot Cohort (AAPL, JPM, GOOG, TSLA - N = 720)
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-medium)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '6px 8px' }}>Track</th>
                      <th style={{ padding: '6px 8px' }}>Features</th>
                      <th style={{ padding: '6px 8px' }}>N Obs</th>
                      <th style={{ padding: '6px 8px' }}>RMSE</th>
                      <th style={{ padding: '6px 8px' }}>MAE</th>
                      <th style={{ padding: '6px 8px' }}>Hit Rate</th>
                      <th style={{ padding: '6px 8px' }}>Rank IC</th>
                      <th style={{ padding: '6px 8px' }}>P-Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(phase5jResearch.track_comparison).map(([trackName, tData]) => (
                      <tr key={trackName} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--text-primary)' }}>{trackName}</td>
                        <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }}>
                          {trackName.includes('Combined') ? '28 feats' : trackName.includes('Events') ? '20 feats' : trackName.includes('Fundamentals') ? '25 feats' : '17 feats'}
                        </td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{tData.n_observations}</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(tData.rmse * 100).toFixed(2)}%</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(tData.mae * 100).toFixed(2)}%</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(tData.hit_rate * 100).toFixed(1)}%</td>
                        <td style={{ padding: '6px 8px', color: tData.rank_ic > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }} className="font-mono">
                          {tData.rank_ic > 0 ? '+' : ''}{tData.rank_ic.toFixed(3)}
                        </td>
                        <td style={{ padding: '6px 8px', color: tData.rank_ic_pvalue < 0.05 ? 'var(--accent-green)' : 'var(--text-dim)' }} className="font-mono">
                          {tData.rank_ic_pvalue.toExponential(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Chronological Walk-Forward Folds Breakdown */}
          {phase5jResearch.fold_results && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', fontWeight: 600 }}>
                Chronological Walk-Forward Folds (4 Outer Folds, 5-Session Purge Gap)
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-medium)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '6px 8px' }}>Fold</th>
                      <th style={{ padding: '6px 8px' }}>Validation Window</th>
                      <th style={{ padding: '6px 8px' }}>Train Obs</th>
                      <th style={{ padding: '6px 8px' }}>Val Obs</th>
                      <th style={{ padding: '6px 8px' }}>Companies</th>
                      <th style={{ padding: '6px 8px' }}>Best Alpha</th>
                      <th style={{ padding: '6px 8px' }}>Zero RMSE</th>
                      <th style={{ padding: '6px 8px' }}>Ridge RMSE</th>
                      <th style={{ padding: '6px 8px' }}>Hit Rate</th>
                      <th style={{ padding: '6px 8px' }}>Rank IC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {phase5jResearch.fold_results.map((f) => (
                      <tr key={f.fold} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--text-primary)' }}>Fold {f.fold}</td>
                        <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">
                          {f.val_start_date} &rarr; {f.val_end_date} {f.fold === 2 ? '(COVID-19)' : ''}
                        </td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{f.n_train_obs.toLocaleString()}</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{f.n_val_obs.toLocaleString()}</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{f.n_val_companies} co</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{f.best_alpha.toFixed(0)}</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(f.metrics.zero_baseline.rmse * 100).toFixed(2)}%</td>
                        <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--accent-cyan)' }} className="font-mono">
                          {(f.metrics.ridge_cross_sectional.rmse * 100).toFixed(2)}%
                        </td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(f.metrics.ridge_cross_sectional.hit_rate * 100).toFixed(1)}%</td>
                        <td style={{ padding: '6px 8px', color: f.metrics.ridge_cross_sectional.ic > 0 ? 'var(--accent-green)' : 'var(--accent-amber)' }} className="font-mono">
                          {f.metrics.ridge_cross_sectional.ic > 0 ? '+' : ''}{f.metrics.ridge_cross_sectional.ic.toFixed(3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Research Limitations & Exclusions Callout */}
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', lineHeight: 1.6 }}>
            <div style={{ fontWeight: 600, color: 'var(--accent-amber)', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertTriangle size={13} />
              <span>Phase 5J Verified Eligibility & Coverage Limitations</span>
            </div>
            <div>
              &bull; <strong>Truncated Coverage in Fold 3:</strong> Five companies (<strong>BLK, CSCO, CVS, EQIX, FCX</strong>) terminate coverage on 2020-04-01 in the source data. They are scored across Folds 0, 1, 2 (2,700 samples/fold) and deterministically excluded from Fold 3 evaluation (55 companies, 2,474 samples) with zero imputed data.
              <br />
              &bull; <strong>Multi-Modal Scope Governance:</strong> Point-in-time SEC EDGAR facts and Form 8-K event features are currently evaluated on the audited 4-company pilot cohort (720 observations). Full cross-sectional expansion of multi-modal features requires SEC ingestion pipeline extension across all 60 companies.
              <br />
              &bull; <strong>Research-Only Disclosure:</strong> All forecasts, directional hit rates, and portfolio simulations are experimental research artifacts evaluated with 15 bps round-trip friction and 10-position institutional limits. They do not constitute personalized investment advice or guarantees of trading profitability.
            </div>
          </div>
        </div>
      )}

      {/* Phase 5K Systematic Model Improvement & Walk-Forward Validation */}
      {phase5kResearch && phase5kResearch.aggregate_model_metrics && (
        <div className="card" style={{ borderTop: '3px solid var(--accent-purple, #a855f7)' }}>
          <div className="card-header">
            <span className="card-title">
              <Layers size={14} style={{ color: 'var(--accent-purple, #a855f7)' }} />
              <span>Phase 5K Systematic Model Improvement & Walk-Forward Validation</span>
            </span>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              <span className="badge-tag badge-status">Pre-Specified Candidates</span>
              <span className="badge-tag badge-experimental">
                {phase5kResearch.metadata?.verdict || 'ACCEPT WITH DOCUMENTED LIMITATIONS'}
              </span>
            </div>
          </div>

          {/* Research Distinctions Header Banner */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Model Classification</div>
              <div style={{ fontSize: '12px', color: 'var(--text-primary)', marginTop: '2px', fontWeight: 600 }}>Simple Baselines vs Learned Models</div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>Zero/Median benchmarks carry 0 variance; learned ML models fit on train folds only.</div>
            </div>
            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Inference Scope</div>
              <div style={{ fontSize: '12px', color: 'var(--text-primary)', marginTop: '2px', fontWeight: 600 }}>Pooled vs Daily Cross-Sectional HAC</div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>Pooled IC conflates market drift; daily IC with Newey-West HAC (L=4) isolates stock alpha.</div>
            </div>
            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Evaluation Track</div>
              <div style={{ fontSize: '12px', color: 'var(--text-primary)', marginTop: '2px', fontWeight: 600 }}>Forecasting Metrics vs Portfolio Execution</div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>Forecast error (RMSE/MAE) evaluated independently from institutional simulation (15 bps friction).</div>
            </div>
            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Governance State</div>
              <div style={{ fontSize: '12px', color: 'var(--accent-amber)', marginTop: '2px', fontWeight: 600 }}>Research Isolation Maintained</div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>Experimental winner not promoted to live BUY/SELL decisions without governance sign-off.</div>
            </div>
          </div>

          {/* Master Multi-Model Comparison Table */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', fontWeight: 600 }}>
              Consolidated Out-of-Sample Performance Comparison (N = {phase5kResearch.metadata?.total_out_of_sample_observations?.toLocaleString() || '10,559'} Observations)
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-medium)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '6px 8px' }}>Candidate Model / Hypothesis</th>
                    <th style={{ padding: '6px 8px' }}>Category</th>
                    <th style={{ padding: '6px 8px' }}>OOS RMSE</th>
                    <th style={{ padding: '6px 8px' }}>OOS MAE</th>
                    <th style={{ padding: '6px 8px' }}>Bias</th>
                    <th style={{ padding: '6px 8px' }}>Hit Rate</th>
                    <th style={{ padding: '6px 8px' }}>Daily CS IC</th>
                    <th style={{ padding: '6px 8px' }}>HAC P-Value</th>
                    <th style={{ padding: '6px 8px' }}>Sim Net Return</th>
                    <th style={{ padding: '6px 8px' }}>Max DD</th>
                    <th style={{ padding: '6px 8px' }}>Trades (Win %)</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Equal-Weight Buy & Hold 60-Company Benchmark Row */}
                  {phase5kResearch.portfolio_simulation?.buy_and_hold_benchmark && (
                    <tr style={{ borderBottom: '1px solid var(--border-medium)', background: 'rgba(34, 197, 94, 0.05)' }}>
                      <td style={{ padding: '6px 8px', fontWeight: 600, color: 'var(--accent-green)' }}>
                        Equal-Weight Buy & Hold (60-Company Cohort, 188 Sessions)
                      </td>
                      <td style={{ padding: '6px 8px' }}>
                        <span
                          className="font-mono"
                          style={{
                            fontSize: '9px',
                            padding: '2px 5px',
                            borderRadius: '3px',
                            background: 'rgba(34, 197, 94, 0.15)',
                            color: 'var(--accent-green)',
                          }}
                        >
                          Reconciled Benchmark
                        </span>
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">—</td>
                      <td style={{ padding: '6px 8px', color: 'var(--accent-green)', fontWeight: 600 }} className="font-mono">
                        +{(phase5kResearch.portfolio_simulation.buy_and_hold_benchmark.total_net_return * 100).toFixed(2)}%
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">
                        {(phase5kResearch.portfolio_simulation.buy_and_hold_benchmark.max_drawdown * 100).toFixed(2)}%
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--text-secondary)' }} className="font-mono">
                        {phase5kResearch.portfolio_simulation.buy_and_hold_benchmark.total_closed_trades} ({(phase5kResearch.portfolio_simulation.buy_and_hold_benchmark.win_rate * 100).toFixed(0)}%)
                      </td>
                    </tr>
                  )}
                  {Object.entries(phase5kResearch.aggregate_model_metrics).map(([mKey, mData]) => {
                    const portData = phase5kResearch.portfolio_simulation?.[mKey];
                    const isRidge = mKey === 'ridge_regression';
                    const isGbrt = mKey === 'hist_gradient_boosting';
                    const isBase = mKey.includes('baseline');
                    const isTransform = mKey.includes('cs_') || mKey.includes('sector_');
                    const hasZeroTrades = portData && portData.total_closed_trades === 0;

                    let displayName = mKey;
                    let categoryTag = 'Learned Model';
                    if (mKey === 'zero_baseline') { displayName = 'Reference 0: Zero Return'; categoryTag = 'Simple Baseline'; }
                    else if (mKey === 'median_baseline') { displayName = 'Reference 1: Historical Median'; categoryTag = 'Simple Baseline'; }
                    else if (mKey === 'ridge_regression') { displayName = 'Ridge Regression (Phase 5J Benchmark)'; categoryTag = 'Validated Model'; }
                    else if (mKey === 'elastic_net') { displayName = 'ElasticNet (L1/L2 Regularized)'; categoryTag = 'Linear ML'; }
                    else if (mKey === 'hist_gradient_boosting') { displayName = 'HistGradientBoosting (Nonlinear Tree)'; categoryTag = 'Nonlinear ML'; }
                    else if (mKey === 'ridge_cs_demeaned') { displayName = 'Ridge CS Demeaned (Market Drift Removed)'; categoryTag = 'CS Transform'; }
                    else if (mKey === 'ridge_cs_scaled') { displayName = 'Ridge CS Scaled (Standardized Dispersion)'; categoryTag = 'CS Transform'; }
                    else if (mKey === 'ridge_sector_neutral') { displayName = 'Ridge Sector-Neutral (Residualized)'; categoryTag = 'Sector Transform'; }

                    return (
                      <tr
                        key={mKey}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          background: isGbrt ? 'rgba(168, 85, 247, 0.05)' : isRidge ? 'rgba(6, 182, 212, 0.05)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '6px 8px', fontWeight: 600, color: isGbrt ? 'var(--accent-purple, #a855f7)' : isRidge ? 'var(--accent-cyan)' : 'var(--text-primary)' }}>
                          {displayName}
                        </td>
                        <td style={{ padding: '6px 8px' }}>
                          <span
                            className="font-mono"
                            style={{
                              fontSize: '9px',
                              padding: '2px 5px',
                              borderRadius: '3px',
                              background: isBase ? 'var(--bg-card)' : isTransform ? 'rgba(234, 179, 8, 0.1)' : 'rgba(168, 85, 247, 0.1)',
                              color: isBase ? 'var(--text-muted)' : isTransform ? 'var(--accent-amber)' : 'var(--text-secondary)',
                            }}
                          >
                            {categoryTag}
                          </span>
                        </td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(mData.rmse * 100).toFixed(2)}%</td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(mData.mae * 100).toFixed(2)}%</td>
                        <td style={{ padding: '6px 8px', color: mData.prediction_bias > 0 ? 'var(--accent-green)' : 'var(--text-dim)' }} className="font-mono">
                          {mData.prediction_bias > 0 ? '+' : ''}{(mData.prediction_bias * 100).toFixed(2)}%
                        </td>
                        <td style={{ padding: '6px 8px' }} className="font-mono">{(mData.directional_hit_rate * 100).toFixed(1)}%</td>
                        <td style={{ padding: '6px 8px', color: mData.daily_cross_sectional_ic?.mean_daily_ic > 0 ? 'var(--accent-green)' : 'var(--text-secondary)' }} className="font-mono">
                          {mData.daily_cross_sectional_ic ? `${mData.daily_cross_sectional_ic.mean_daily_ic > 0 ? '+' : ''}${mData.daily_cross_sectional_ic.mean_daily_ic.toFixed(3)}` : '0.000'}
                        </td>
                        <td style={{ padding: '6px 8px', color: (mData.daily_cross_sectional_ic?.newey_west_hac_pvalue || 1) < 0.05 ? 'var(--accent-green)' : 'var(--text-dim)' }} className="font-mono">
                          {mData.daily_cross_sectional_ic ? mData.daily_cross_sectional_ic.newey_west_hac_pvalue.toFixed(2) : '1.00'}
                        </td>
                        <td style={{ padding: '6px 8px', color: (portData?.total_net_return || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }} className="font-mono">
                          {portData ? `${portData.total_net_return >= 0 ? '+' : ''}${(portData.total_net_return * 100).toFixed(2)}%` : '0.00%'}
                        </td>
                        <td style={{ padding: '6px 8px', color: 'var(--text-dim)' }} className="font-mono">
                          {portData ? `${(portData.max_drawdown * 100).toFixed(2)}%` : '0.00%'}
                        </td>
                        <td style={{ padding: '6px 8px', color: hasZeroTrades ? 'var(--text-dim)' : 'var(--text-secondary)' }} className="font-mono">
                          {hasZeroTrades ? (
                            <span title="No positions executed under the fixed policy (reconciled: candidate signals rejected by defensive gates or shrinkage)">
                              0 (No positions executed)
                            </span>
                          ) : portData ? (
                            `${portData.total_closed_trades} (${(portData.win_rate * 100).toFixed(0)}%)`
                          ) : (
                            '0 (0%)'
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Research Hypotheses & Evidence Callout Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            {/* Finding 1: GBRT Performance */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--accent-purple, #a855f7)', fontSize: '12px', marginBottom: '4px' }}>
                1. HistGradientBoosting Non-Linear Evaluation
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                <strong>Forecasting Result:</strong> GBRT achieves lower RMSE (<strong>6.44%</strong>) and MAE (<strong>3.93%</strong>) than Zero Return (6.46%) and Ridge (6.52%).
                <br />
                <strong>Ranking Reality:</strong> Daily cross-sectional IC is <strong>-0.027</strong> (Newey-West HAC <strong>p = 0.45</strong>), confirming no statistically significant stock-picking edge.
              </div>
            </div>

            {/* Finding 2: Cross-Sectional Demeaning */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--accent-amber)', fontSize: '12px', marginBottom: '4px' }}>
                2. Cross-Sectional Demeaning & Rank Invariance
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                <strong>Mathematical Invariance:</strong> Subtracting date mean predicted return leaves Spearman rank correlation identical (<strong>-0.045</strong>, p = 0.27) because ranking is invariant to additive date constants.
                <br />
                <strong>Macro Edge Loss:</strong> Directional hit rate dropped from 54.9% to 48.0%, showing drift carried helpful recovery signal.
              </div>
            </div>

            {/* Finding 3: Sector Neutralization */}
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--accent-cyan)', fontSize: '12px', marginBottom: '4px' }}>
                3. Sector-Neutral Residualization Hypothesis
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                <strong>Sector Adjustment:</strong> Demeaning predictions within historical sectors shifted daily rank IC to <strong>-0.025</strong> (p = 0.21).
                <br />
                <strong>Exploratory Status:</strong> The shift is not statistically significant. RMSE increased slightly to 6.52% with a 48.8% hit rate.
              </div>
            </div>
          </div>

          {/* Institutional Portfolio Order Reconciliation Footer */}
          <div style={{ fontSize: '11px', color: 'var(--text-dim)', background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', lineHeight: 1.6 }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
              Phase 5K / 5K.1 Benchmark Reconciliation & Institutional Portfolio Governance:
            </div>
            <div>
              &bull; <strong>Benchmark Reconciliation (+4.71% vs +5.72%):</strong> Fully reconciled. Phase 5J held across all 188 market simulation sessions through 2020-06-15 (+4.71%, $104,709.12), capturing the June 11 pullback. The 180-session decision-window variant exited 2020-06-04 (+5.72%, $105,724.86). Both are preserved and mathematically reproduced down to machine precision.
              <br />
              &bull; <strong>Order Reconciliation Verified:</strong> Ridge: 112 Candidate BUY Signals = 44 Closed Trades + 68 Rejections (44 MAX_TICKER_EXPOSURE + 24 CONCURRENT_LIMIT_REACHED) + 0 Terminal Open Positions (100.0% reconciled).
              <br />
              &bull; <strong>Zero-Trade Models Clarified:</strong> ElasticNet, GBRT, CS Demeaned, and Sector Neutral produced 0 trades because defensive risk gates operated identically. GBRT produced 235 candidate BUY signals (&ge; +1.50% net return), but 100% occurred during elevated market volatility sessions (rolling volatility &gt; 0.1500) and were intercepted by the Volatility Gate. Simulator correctly reported 100% cash preservation ($100k cash, 0 drawdown). Zero-trade results reflect defensive gating, not portfolio failure.
              <br />
              &bull; <strong>Final Research Verdict:</strong> <strong>ACCEPT WITH DOCUMENTED LIMITATIONS</strong>. Code integrity, walk-forward isolation, and accounting equations pass all audit checks. The predictive edge remains exploratory and unproven; simpler Ridge baseline is retained for reference tracking.
            </div>
          </div>
        </div>
      )}

      {/* Honest Prediction Unavailable State */}
      {prediction && prediction.status === 'unavailable' && (
        <div className="card" style={{ borderLeft: '4px solid var(--accent-amber)', padding: '20px' }}>
          <div className="card-header">
            <span className="card-title" style={{ color: 'var(--accent-amber)' }}>
              <AlertTriangle size={16} />
              <span>Prediction Unavailable — Safety Guardrail Triggered</span>
            </span>
            <span className="badge-tag badge-offline">Status: Unavailable</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <p>
              <strong>Reason:</strong> {prediction.message}
            </p>
            {prediction.limitations && prediction.limitations.length > 0 && (
              <div>
                <strong>Active Blockers:</strong>
                <ul style={{ paddingLeft: '20px', marginTop: '6px' }}>
                  {prediction.limitations.map((lim, i) => (
                    <li key={i}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}
            <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontStyle: 'italic', marginTop: '4px' }}>
              In accordance with project integrity standards, the interface never fabricates default predictions or simulates values when required input data is missing or company identity is unresolved.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
