import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Play,
  Cpu,
  AlertOctagon,
  CheckCircle2,
  Layers,
  Database,
} from 'lucide-react';

export default function PredictionResearchTab({
  selectedTicker,
  companyMeta,
  marketData,
  onSelectCompany,
}) {
  // Runtime inference state
  const [prediction, setPrediction] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loadingRuntime, setLoadingRuntime] = useState(false);
  const [runtimeError, setRuntimeError] = useState('');
  const [asOfDate, setAsOfDate] = useState('');

  // Archived predictions state (Phase 5K)
  const [archivedData, setArchivedData] = useState(null);
  const [selectedModel, setSelectedModel] = useState('ridge_regression');
  const [selectedFold, setSelectedFold] = useState('all');
  const [loadingArchived, setLoadingArchived] = useState(false);
  const [archivedError, setArchivedError] = useState('');

  // Research summary state (Phase 5H portfolio research)
  const [portfolioResearch, setPortfolioResearch] = useState(null);

  // Load Phase 5H portfolio simulation research summary
  useEffect(() => {
    fetch('/api/models/portfolio/research')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.strategy_results) setPortfolioResearch(data);
      })
      .catch((err) => console.error('Error fetching portfolio research:', err));
  }, []);

  // Reset asOfDate when selectedTicker changes to guarantee clean date alignment
  useEffect(() => {
    setAsOfDate('');
  }, [selectedTicker]);

  // Sync date from market series if asOfDate is empty
  useEffect(() => {
    if (marketData && marketData.series && marketData.series.length > 0 && !asOfDate) {
      const latest = marketData.series[marketData.series.length - 1].trading_date;
      setAsOfDate(latest);
    }
  }, [marketData, asOfDate]);

  // Fetch runtime inference whenever selectedTicker changes
  useEffect(() => {
    if (!selectedTicker) return;
    let isCurrent = true;
    setLoadingRuntime(true);
    setRuntimeError('');

    Promise.all([
      fetch('/api/models/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: selectedTicker, as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
      fetch('/api/models/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: selectedTicker, as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
    ])
      .then(([predData, decData]) => {
        if (isCurrent) {
          setPrediction(predData);
          setDecision(decData);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          console.error('Error requesting prediction & decision:', err);
          setRuntimeError('Failed to connect to runtime inference API endpoint.');
        }
      })
      .finally(() => {
        if (isCurrent) setLoadingRuntime(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedTicker, asOfDate]);

  // Fetch Phase 5K Archived Predictions whenever selectedTicker, selectedModel, or selectedFold changes
  useEffect(() => {
    if (!selectedTicker) return;
    let isCurrent = true;
    setLoadingArchived(true);
    setArchivedError('');

    let url = `/api/research/companies/${selectedTicker}/predictions?model_id=${selectedModel}&limit=200`;
    if (selectedFold !== 'all') {
      url += `&fold=${selectedFold}`;
    }

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch archived predictions`);
        return res.json();
      })
      .then((data) => {
        if (isCurrent) {
          setArchivedData(data);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          console.error('Error loading archived predictions:', err);
          setArchivedError(err.message);
          setArchivedData(null);
        }
      })
      .finally(() => {
        if (isCurrent) setLoadingArchived(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedTicker, selectedModel, selectedFold]);

  const handleRunManualInference = (e) => {
    e.preventDefault();
    if (!selectedTicker) return;
    setLoadingRuntime(true);
    setRuntimeError('');
    Promise.all([
      fetch('/api/models/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: selectedTicker, as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
      fetch('/api/models/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: selectedTicker, as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
    ])
      .then(([predData, decData]) => {
        setPrediction(predData);
        setDecision(decData);
      })
      .catch((_err) => {
        setRuntimeError('Failed to connect to runtime inference API endpoint.');
      })
      .finally(() => {
        setLoadingRuntime(false);
      });
  };

  const handleTestExcludedCompany = () => {
    setLoadingRuntime(true);
    setRuntimeError('');
    Promise.all([
      fetch('/api/models/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: 'AA', as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
      fetch('/api/models/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: 'AA', as_of_date: asOfDate || undefined }),
      }).then((r) => r.json()),
    ])
      .then(([predData, decData]) => {
        setPrediction(predData);
        setDecision(decData);
      })
      .catch((_err) => {
        setRuntimeError('Failed to execute guardrail check on AA.');
      })
      .finally(() => {
        setLoadingRuntime(false);
      });
  };

  const isPrototype = ['AAPL', 'JPM', 'GOOG', 'TSLA'].includes(selectedTicker);

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

      {/* Control Panel: Company Selector & Decision Date */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">
            <Cpu size={14} />
            <span>Forward Return Prediction & Research Navigator</span>
          </span>
          <span className="badge-tag badge-status">
            Active: <strong>{selectedTicker}</strong> ({companyMeta?.company_name || selectedTicker})
          </span>
        </div>

        <form onSubmit={handleRunManualInference} style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase' }}>
              Prototype Pilot Quick-Select
            </label>
            <div className="company-pills">
              {['AAPL', 'JPM', 'GOOG', 'TSLA'].map((t) => (
                <button
                  type="button"
                  key={t}
                  className={`company-pill ${selectedTicker === t ? 'active' : ''}`}
                  onClick={() => onSelectCompany(t)}
                  id={`pred-pill-${t}`}
                >
                  {t}
                </button>
              ))}
              {!isPrototype && (
                <button type="button" className="company-pill active" id={`pred-pill-active-${selectedTicker}`}>
                  {selectedTicker} (Active Cohort)
                </button>
              )}
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
              disabled={loadingRuntime}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '7px 16px' }}
              id="btn-run-prediction"
            >
              <Play size={12} />
              <span>{loadingRuntime ? 'Evaluating...' : 'Test Runtime Inference'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* =========================================================================
          SECTION A: RUNTIME MODEL INFERENCE (LIVE / EXPERIMENTAL)
          ========================================================================= */}
      <div className="card" style={{ borderLeft: isPrototype ? '4px solid var(--accent-blue)' : '4px solid var(--accent-amber)' }}>
        <div className="card-header">
          <span className="card-title">
            <Cpu size={14} style={{ color: isPrototype ? 'var(--accent-blue)' : 'var(--accent-amber)' }} />
            <span>Capability Dimension A: Runtime Model Inference</span>
          </span>
          <span className={`badge-tag ${isPrototype ? 'badge-status' : 'badge-experimental'}`}>
            {isPrototype ? 'Prototype Supported' : 'Historical Research Only'}
          </span>
        </div>

        {runtimeError && (
          <div style={{ padding: '12px', color: 'var(--accent-red)', fontSize: '12px' }}>
            {runtimeError}
          </div>
        )}

        {prediction && prediction.status === 'available' ? (
          <div className="terminal-grid">
            <div className="card" style={{ gridColumn: 'span 7' }}>
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
                    Decimal: {prediction.predicted_forward_return?.toFixed(6)}
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

              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '12px', marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
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
            </div>

            <div className="card" style={{ gridColumn: 'span 5' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Features Utilized ({prediction.features_used?.length || 0} Inputs)
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {prediction.features_used?.map((feat) => (
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
        ) : (
          <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '12px' }}>
            <div style={{ fontWeight: 600, color: 'var(--accent-amber)', marginBottom: '4px' }}>
              Runtime Model Inference Unsupported for {selectedTicker}
            </div>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {prediction?.message ||
                `Runtime model weights are currently fitted exclusively for the 4-company prototype pilot catalog (AAPL, JPM, GOOG, TSLA). Runtime inference is honest: no simulated predictions or synthetic zeros are generated.`}
            </p>
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
              &rarr; Retrospective out-of-sample forward-return predictions for <strong>{selectedTicker}</strong> are fully available from the <strong>Phase 5K Historical Research Archive</strong> below.
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
          SECTION B: PHASE 5K HISTORICAL OUT-OF-SAMPLE PREDICTIONS ARCHIVE
          ========================================================================= */}
      <div className="card" style={{ borderLeft: '4px solid var(--accent-purple, #a855f7)' }}>
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className="card-title">
              <Database size={14} style={{ color: 'var(--accent-purple, #a855f7)' }} />
              <span>Capability Dimension B: Phase 5K Historical Out-of-Sample Predictions Archive</span>
            </span>
            <span className="badge-tag badge-status">
              {archivedData?.total_records ? `${archivedData.total_records} Records` : 'Research Archive'}
            </span>
          </div>

          <div className="chart-controls">
            {/* Candidate Model Selector */}
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="company-select-dropdown"
              style={{ maxWidth: '200px' }}
              id="select-oos-model"
              aria-label="Select Candidate Model for Out-of-Sample Predictions"
            >
              <option value="ridge_regression">Model 1: Ridge Regression</option>
              <option value="elastic_net">Model 2: Elastic Net</option>
              <option value="hist_gradient_boosting">Model 3: Hist Gradient Boosting</option>
              <option value="ridge_cs_demeaned">Model 4: Ridge CS Demeaned</option>
              <option value="ridge_cs_scaled">Model 5: Ridge CS Scaled</option>
              <option value="ridge_sector_neutral">Model 6: Ridge Sector Neutral</option>
              <option value="median_baseline">Ref 1: Historical Median</option>
              <option value="zero_baseline">Ref 0: Zero Return</option>
            </select>

            {/* Fold Filter */}
            {['all', '0', '1', '2', '3'].map((f) => (
              <button
                type="button"
                key={f}
                className={`chart-toggle-btn ${selectedFold === f ? 'active' : ''}`}
                onClick={() => setSelectedFold(f)}
                id={`btn-fold-${f}`}
              >
                {f === 'all' ? 'All Folds' : `Fold ${f}`}
              </button>
            ))}
          </div>
        </div>

        {/* Strict Definition Clarification */}
        <div style={{ background: 'rgba(168, 85, 247, 0.08)', border: '1px solid rgba(168, 85, 247, 0.25)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          <strong>POINT-IN-TIME RESEARCH SEMANTICS:</strong> All records reflect out-of-sample forward return predictions generated by walk-forward models fit strictly on training partitions with 5-session purge gaps.{' '}
          <strong style={{ color: 'var(--text-primary)' }}>Predicted Return</strong> is the model point forecast.{' '}
          <strong style={{ color: 'var(--accent-blue)' }}>Realized Forward Return</strong> reflects actual historical price action (T+1 open &rarr; T+5 close) and is <em>never</em> a model prediction.{' '}
          <strong style={{ color: 'var(--accent-amber)' }}>Residual</strong> represents forecast error (<span className="font-mono">Realized - Predicted</span>).
        </div>

        {loadingArchived ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="font-mono">Loading archived predictions for {selectedTicker} ({selectedModel})...</span>
          </div>
        ) : archivedError ? (
          <div style={{ padding: '20px', color: 'var(--accent-red)', fontSize: '12px' }}>
            Failed to load archived predictions: {archivedError}
          </div>
        ) : !archivedData || archivedData.predictions?.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No out-of-sample prediction records found for <strong>{selectedTicker}</strong> under model <span className="font-mono">{selectedModel}</span> {selectedFold !== 'all' ? `(Fold ${selectedFold})` : ''}.
            {archivedData?.is_truncated && selectedFold === '3' && (
              <div style={{ color: 'var(--accent-amber)', marginTop: '6px', fontSize: '11px' }}>
                Note: {selectedTicker} is a truncated constituent (April 2020 cutoff); Fold 3 is deterministically unobserved.
              </div>
            )}
          </div>
        ) : (
          <div className="terminal-table-wrapper" style={{ maxHeight: '340px', overflowY: 'auto' }}>
            <table className="terminal-table">
              <thead>
                <tr>
                  <th>Decision Date (T Close)</th>
                  <th>Fold</th>
                  <th>Model Identifier</th>
                  <th>Predicted Return (ŷ)</th>
                  <th>Realized Return (y)</th>
                  <th>Residual Error (e)</th>
                  <th>Train Uncertainty (σ)</th>
                  <th>Adj Close ($)</th>
                </tr>
              </thead>
              <tbody>
                {archivedData.predictions.map((p, idx) => (
                  <tr key={`${p.trading_date}-${p.model_id}-${idx}`}>
                    <td className="font-mono">{p.trading_date}</td>
                    <td className="font-mono">Fold {p.fold}</td>
                    <td className="font-mono" style={{ color: 'var(--accent-purple, #a855f7)' }}>{p.model_id}</td>
                    <td className="font-mono" style={{ color: p.predicted_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
                      {p.predicted_return >= 0 ? '+' : ''}{(p.predicted_return * 100).toFixed(2)}%
                    </td>
                    <td className="font-mono" style={{ color: p.target_return >= 0 ? 'var(--accent-blue)' : 'var(--text-secondary)' }}>
                      {p.target_return >= 0 ? '+' : ''}{(p.target_return * 100).toFixed(2)}%
                    </td>
                    <td className="font-mono" style={{ color: Math.abs(p.residual) > 0.05 ? 'var(--accent-amber)' : 'var(--text-dim)' }}>
                      {p.residual >= 0 ? '+' : ''}{(p.residual * 100).toFixed(2)}%
                    </td>
                    <td className="font-mono" style={{ color: 'var(--text-dim)' }}>
                      ±{(p.sigma_train * 100).toFixed(2)}%
                    </td>
                    <td className="font-mono">${p.adjusted_close.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {archivedData && (
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '10px', fontSize: '11px', color: 'var(--text-dim)' }}>
            <span>
              Showing {archivedData.returned_records} of {archivedData.total_records} observations for {selectedTicker} ({archivedData.earliest_date} &rarr; {archivedData.latest_date})
            </span>
            <span className="font-mono">
              Source: {archivedData.source_artifact}
            </span>
          </div>
        )}
      </div>

      {/* =========================================================================
          SECTION C: PHASE 5G / 5L DECISION FUNNEL & RISK GATES
          ========================================================================= */}
      {decision && (
        <div className="card" style={{ borderTop: '3px solid ' + (decision.signal === 'BUY' ? 'var(--accent-green)' : decision.signal === 'SELL' ? 'var(--accent-red)' : 'var(--accent-amber)') }}>
          <div className="card-header">
            <span className="card-title">
              <ShieldAlert size={14} style={{ color: decision.signal === 'BUY' ? 'var(--accent-green)' : decision.signal === 'SELL' ? 'var(--accent-red)' : 'var(--accent-amber)' }} />
              <span>Phase 5G Decision & Risk Funnel (8-Stage Institutional Gating)</span>
            </span>
            <span className={`badge-tag ${decision.signal === 'BUY' ? 'badge-status' : decision.signal === 'SELL' ? 'badge-experimental' : 'badge-offline'}`}>
              Candidate Signal: {decision.signal}
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
              Defensive Risk Gates Status ({decision.risk_checks_passed?.length || 0} Passed, {decision.risk_checks_failed?.length || 0} Failed)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '6px' }}>
              {decision.risk_checks_passed?.map((chk, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--accent-green)' }}>
                  <CheckCircle2 size={13} style={{ flexShrink: 0 }} />
                  <span>{chk}</span>
                </div>
              ))}
              {decision.risk_checks_failed?.map((chk, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--accent-red)' }}>
                  <AlertOctagon size={13} style={{ flexShrink: 0 }} />
                  <span>{chk}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          SECTION D: PHASE 5H PORTFOLIO SIMULATION & LEAKAGE-SAFE VALIDATION
          ========================================================================= */}
      {portfolioResearch && portfolioResearch.strategy_results && (
        <div className="card" style={{ borderTop: '3px solid var(--accent-blue)' }}>
          <div className="card-header">
            <span className="card-title">
              <Layers size={14} style={{ color: 'var(--accent-blue)' }} />
              <span>Phase 5H Portfolio Simulation & Rolling Threshold Validation (Research)</span>
            </span>
            <span className="badge-tag badge-status">Audited 4-Fold Panel (N = 720)</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Cash Benchmark</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                $100,000.00
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>Net Ret: 0.00% | Max DD: 0.00%</div>
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
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Rolling Threshold Policy</div>
              <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: portfolioResearch.strategy_results.rolling_threshold_policy.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                ${portfolioResearch.strategy_results.rolling_threshold_policy.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                Net: {(portfolioResearch.strategy_results.rolling_threshold_policy.total_net_return * 100).toFixed(2)}% | Win: {(portfolioResearch.strategy_results.rolling_threshold_policy.win_rate * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
