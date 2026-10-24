import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import {
  Award,
  FileSpreadsheet,
  AlertTriangle,
  Layers,
  Database,
  ShieldAlert,
  TrendingDown,
} from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

export default function ModelLabTab({ evalData, loading, selectedTicker, companyMeta }) {
  const [activeResearchPhase, setActiveResearchPhase] = useState('phase5d'); // 'phase5d', 'phase5j', 'phase5k', 'phase8'
  const [activeCohort, setActiveCohort] = useState('panel'); // for Phase 5D: 'panel' or 'two_company'
  const [phase5jData, setPhase5jData] = useState(null);
  const [phase5kData, setPhase5kData] = useState(null);
  const [phase8Data, setPhase8Data] = useState(null);

  // Fetch Phase 8 financial reports research summary
  useEffect(() => {
    fetch('/api/models/research/phase8')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.status === 'available') {
          setPhase8Data(data);
        }
      })
      .catch((err) => console.error('Failed to load Phase 8 research:', err));
  }, []);

  // Fetch Phase 5J research summary
  useEffect(() => {
    fetch('/api/models/research/phase5j')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && (data.status === 'available' || data.aggregate_metrics)) {
          setPhase5jData(data);
        }
      })
      .catch((err) => console.error('Failed to load Phase 5J research:', err));
  }, []);

  // Fetch Phase 5K model improvement research summary
  useEffect(() => {
    fetch('/api/models/research/phase5k')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && (data.status === 'available' || data.aggregate_model_metrics)) {
          setPhase5kData(data);
        }
      })
      .catch((err) => console.error('Failed to load Phase 5K research:', err));
  }, []);

  if (loading || !evalData) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <p className="font-mono">Loading model evaluation repository and fold-level metrics...</p>
      </div>
    );
  }

  const folds = activeCohort === 'panel' ? evalData.fold_results : evalData.two_company_cohort_results;
  const holdoutFold = evalData.fold_results ? evalData.fold_results.find((f) => f.fold === 3) : null;

  const barChartData = {
    labels: [
      'Ref 0: Zero Return',
      'Ref 1: Historical Median',
      'Model 1: Market-Only Ridge',
      'Model 2: Market + Fundamentals',
    ],
    datasets: [
      {
        label: 'Holdout MAE (Lower is Better)',
        data: [
          holdoutFold ? holdoutFold.zero_mae : 0.0536,
          holdoutFold ? holdoutFold.median_mae : 0.0502,
          holdoutFold ? holdoutFold.market_ridge_mae : 0.0497,
          holdoutFold ? holdoutFold.fund_ridge_mae : 0.0504,
        ],
        backgroundColor: [
          'rgba(148, 163, 184, 0.6)',
          'rgba(245, 158, 11, 0.6)',
          'rgba(59, 130, 246, 0.8)',
          'rgba(6, 182, 212, 0.6)',
        ],
        borderColor: ['#94a3b8', '#f59e0b', '#3b82f6', '#06b6d4'],
        borderWidth: 1.5,
      },
    ],
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0c1017',
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
        borderColor: '#1c2638',
        borderWidth: 1,
        callbacks: {
          label: (ctx) => `Holdout MAE: ${ctx.parsed.y.toFixed(4)}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(28, 38, 56, 0.4)' },
        ticks: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } },
      },
      y: {
        grid: { color: 'rgba(28, 38, 56, 0.4)' },
        ticks: {
          color: '#64748b',
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (v) => v.toFixed(3),
        },
        min: 0.04,
        max: 0.06,
      },
    },
  };

  // Derived eligibility from active company capability
  const evalTracks = companyMeta?.capability?.evaluation_tracks;
  const evalWindow = companyMeta?.capability?.evaluation_window;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Prominent Provenance Callout */}
      <div className="disclaimer-banner" style={{ borderLeftColor: 'var(--accent-blue)' }}>
        <FileSpreadsheet size={16} style={{ color: 'var(--accent-blue)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong style={{ color: 'var(--accent-blue)' }}>EVALUATION PROVENANCE:</strong>{' '}
          <span className="font-mono">
            {activeResearchPhase === 'phase5d'
              ? evalData.provenance
              : activeResearchPhase === 'phase5j'
              ? 'Phase 5J Validated 60-Company Cross-Sectional Report (docs/phase5j_cross_sectional_evaluation_report.md)'
              : activeResearchPhase === 'phase5k'
              ? 'Phase 5K Systematic Model Improvement Report (docs/phase5k_model_improvement_report.md)'
              : 'Phase 8 Financial Reports Specialist Model Report (docs/PHASE_8_FINAL_ACCEPTANCE_REPORT.md)'}
          </span>
          . All reported scores reflect audited 4-fold walk-forward validation with 5-session purge gaps and training-only preprocessing.
        </div>
      </div>

      {/* Critical Quantitative Limitation Banner */}
      <div className="disclaimer-banner">
        <AlertTriangle size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>CRITICAL QUANTITATIVE LIMITATION:</strong> Lower forward return-prediction error (MAE/RMSE) does{' '}
          <strong>NOT</strong> establish trading profitability, execution feasibility, or positive portfolio Sharpe ratios.
          Transaction costs (15 bps round-trip friction), bid-ask spreads, and borrowing costs significantly impact real-world execution.
          Historical evaluation performance does not guarantee future trading profitability.
        </div>
      </div>

      {/* Active Company Research Eligibility Card */}
      {selectedTicker && (
        <div className="card" style={{ borderLeft: '3px solid var(--accent-cyan)' }}>
          <div className="card-header">
            <span className="card-title">
              <Database size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span>
                Active Company Evaluation Eligibility: <strong>{selectedTicker}</strong> ({companyMeta?.company_name || selectedTicker})
              </span>
            </span>
            <span className="badge-tag badge-status font-mono">
              CIK: {companyMeta?.cik || 'Unindexed'} | Sector: {companyMeta?.sector || 'N/A'}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', fontSize: '11px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Track A (Market-Only)</div>
              <div style={{ color: 'var(--accent-green)', fontWeight: 700, marginTop: '2px' }}>
                ELIGIBLE (17 Features)
              </div>
              <div style={{ color: 'var(--text-dim)', fontSize: '10px' }}>Daily OHLCV, adjusted returns, volatility</div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Track B (Market + SEC Facts)</div>
              <div style={{ color: evalTracks?.track_b_market_plus_fund ? 'var(--accent-green)' : 'var(--text-muted)', fontWeight: 700, marginTop: '2px' }}>
                {evalTracks?.track_b_market_plus_fund ? 'ELIGIBLE (25 Features)' : 'INELIGIBLE (Pilot Unobserved)'}
              </div>
              <div style={{ color: 'var(--text-dim)', fontSize: '10px' }}>Point-in-time SEC 10-K/10-Q XBRL ratios</div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Track C (Market + Events)</div>
              <div style={{ color: evalTracks?.track_c_market_plus_events ? 'var(--accent-green)' : 'var(--text-muted)', fontWeight: 700, marginTop: '2px' }}>
                {evalTracks?.track_c_market_plus_events ? 'ELIGIBLE (20 Features)' : 'INELIGIBLE (8-K Unobserved)'}
              </div>
              <div style={{ color: 'var(--text-dim)', fontSize: '10px' }}>SEC Form 8-K material event features</div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Walk-Forward Folds</div>
              <div style={{ color: 'var(--text-primary)', fontWeight: 700, marginTop: '2px' }}>
                {evalTracks?.eligible_folds?.length
                  ? evalTracks.eligible_folds.map((f) => `Fold ${f}`).join(', ')
                  : evalWindow?.is_truncated
                  ? 'Folds 0, 1, 2 (Fold 3 Excluded)'
                  : 'Folds 0, 1, 2, 3 (Full Panel)'}
              </div>
              <div style={{ color: evalWindow?.is_truncated ? 'var(--accent-amber)' : 'var(--accent-blue)', fontSize: '10px' }}>
                Coverage: {evalWindow?.descriptive_category || 'COMPLETE'} ({evalWindow?.observed_window_sessions || 363} sessions)
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Research Phase Navigation */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span className="card-title">
              <Layers size={14} />
              <span>Research Program Evaluation Suite</span>
            </span>
            <div className="chart-controls">
              <button
                className={`chart-toggle-btn ${activeResearchPhase === 'phase5d' ? 'active' : ''}`}
                onClick={() => setActiveResearchPhase('phase5d')}
                id="btn-eval-phase5d"
              >
                Phase 5D: Prototype Pilot (4 Co)
              </button>
              <button
                className={`chart-toggle-btn ${activeResearchPhase === 'phase5j' ? 'active' : ''}`}
                onClick={() => setActiveResearchPhase('phase5j')}
                id="btn-eval-phase5j"
              >
                Phase 5J: Cross-Sectional (60 Co)
              </button>
              <button
                className={`chart-toggle-btn ${activeResearchPhase === 'phase5k' ? 'active' : ''}`}
                onClick={() => setActiveResearchPhase('phase5k')}
                id="btn-eval-phase5k"
              >
                Phase 5K: Model Improvement (8 Candidates)
              </button>
              <button
                className={`chart-toggle-btn ${activeResearchPhase === 'phase8' ? 'active' : ''}`}
                onClick={() => setActiveResearchPhase('phase8')}
                id="btn-eval-phase8"
              >
                Phase 8: Financial Reports Specialist (305 Co)
              </button>
            </div>
          </div>
        </div>

        {/* =========================================================================
            VIEW 1: PHASE 5D — PROTOTYPE PILOT COHORT (4 COMPANIES)
            ========================================================================= */}
        {activeResearchPhase === 'phase5d' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Holdout Comparison Chart & Key Protocol Invariants */}
            <div className="terminal-grid">
              <div className="card" style={{ gridColumn: 'span 7' }}>
                <div className="card-header">
                  <span className="card-title">
                    <Award size={14} />
                    <span>Phase 5D Final Holdout Comparison (Fold 3: 2020-03-31 → 2020-06-03)</span>
                  </span>
                  <span className="badge-tag badge-status">Lower is Better</span>
                </div>

                <div style={{ height: '240px' }}>
                  <Bar data={barChartData} options={barOptions} />
                </div>
                <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center' }}>
                  Winner on Untouched Holdout: <strong>Model 1 (Market-Only Ridge: 0.0497 MAE)</strong> beats Median (0.0502) and Market+Fundamentals (0.0504).
                </div>
              </div>

              <div className="card" style={{ gridColumn: 'span 5' }}>
                <div className="card-header">
                  <span className="card-title">Walk-Forward Protocol Invariants</span>
                  <span className="badge-tag badge-experimental">Audited</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
                  <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Target Definition</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{evalData.target_definition}</div>
                  </div>

                  <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Purge Requirement</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                      Strict 5-trading-day purge between train end and validation start. Zero label overlap leakage.
                    </div>
                  </div>

                  <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Hyperparameter Selection</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                      L2 regularization alpha tuned strictly on training partitions (alpha=1000.0 selected).
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Cohort Selector and Fold-Level Evaluation Table */}
            <div className="card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span className="card-title">Walk-Forward Fold-Level Metrics & Regime Breakdown</span>
                  <div className="chart-controls">
                    <button
                      className={`chart-toggle-btn ${activeCohort === 'panel' ? 'active' : ''}`}
                      onClick={() => setActiveCohort('panel')}
                      id="cohort-panel-btn"
                    >
                      Full 4-Company Panel (1,432 rows)
                    </button>
                    <button
                      className={`chart-toggle-btn ${activeCohort === 'two_company' ? 'active' : ''}`}
                      onClick={() => setActiveCohort('two_company')}
                      id="cohort-twocomp-btn"
                    >
                      Complete Fundamentals Cohort (AAPL + JPM)
                    </button>
                  </div>
                </div>
                <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  4 Chronological Folds
                </span>
              </div>

              <div className="terminal-table-wrapper">
                <table className="terminal-table">
                  <thead>
                    <tr>
                      <th>Fold</th>
                      <th>Regime & Dates</th>
                      <th>Train Rows</th>
                      <th>Val Rows</th>
                      <th>Zero MAE</th>
                      <th>Median MAE</th>
                      <th>Market Ridge MAE</th>
                      <th>Mkt+Fund MAE</th>
                      <th>Market IC</th>
                      <th>Winner (MAE)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {folds.map((fold) => (
                      <tr key={fold.fold} id={`fold-row-${fold.fold}`}>
                        <td className="font-mono">
                          <strong>Fold {fold.fold}</strong> {fold.fold === 3 ? '(Holdout)' : ''}
                        </td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{fold.regime_notes}</div>
                          <div className="font-mono" style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                            Val: {fold.val_start} → {fold.val_end}
                          </div>
                        </td>
                        <td className="font-mono">{fold.train_rows}</td>
                        <td className="font-mono">{fold.val_rows}</td>
                        <td className="font-mono">{fold.zero_mae.toFixed(4)}</td>
                        <td className="font-mono">{fold.median_mae.toFixed(4)}</td>
                        <td className="font-mono" style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
                          {fold.market_ridge_mae.toFixed(4)}
                        </td>
                        <td className="font-mono" style={{ color: 'var(--accent-cyan)' }}>
                          {fold.fund_ridge_mae ? fold.fund_ridge_mae.toFixed(4) : 'N/A'}
                        </td>
                        <td className={`font-mono ${fold.market_ridge_ic >= 0 ? 'text-positive' : 'text-negative'}`}>
                          {fold.market_ridge_ic >= 0 ? '+' : ''}
                          {fold.market_ridge_ic.toFixed(3)}
                        </td>
                        <td>
                          <span className="badge-tag badge-status">{fold.best_model_mae}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Critical Findings Bullet Cards */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">Audited Research Conclusions & Empirical Insights</span>
                <span className="badge-tag badge-status">Phase 5D Report Findings</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                {evalData.critical_findings.map((finding, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '12px',
                      fontSize: '12px',
                      lineHeight: 1.6,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <div style={{ color: 'var(--accent-blue)', fontWeight: 700, marginBottom: '4px' }}>
                      Finding {idx + 1}
                    </div>
                    <p>{finding}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            VIEW 2: PHASE 5J — VALIDATED 60-COMPANY CROSS-SECTIONAL COHORT
            ========================================================================= */}
        {activeResearchPhase === 'phase5j' && phase5jData && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Phase 5J Aggregate Summary Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Reference 0 (Zero Return)</div>
                <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-secondary)' }}>
                  {(phase5jData.aggregate_metrics.reference_0_zero.rmse * 100).toFixed(2)}% RMSE
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  MAE: {(phase5jData.aggregate_metrics.reference_0_zero.mae * 100).toFixed(2)}% | Directional Hit: 50.0%
                </div>
              </div>

              <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model 1 (Cross-Sectional Ridge)</div>
                <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                  {(phase5jData.aggregate_metrics.ridge_cross_sectional.rmse * 100).toFixed(2)}% RMSE
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  MAE: {(phase5jData.aggregate_metrics.ridge_cross_sectional.mae * 100).toFixed(2)}% | Hit Rate: {(phase5jData.aggregate_metrics.ridge_cross_sectional.hit_rate * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Daily CS IC: +{phase5jData.aggregate_metrics.ridge_cross_sectional.daily_cross_sectional_ic?.mean_daily_ic.toFixed(3)} (HAC p = {phase5jData.aggregate_metrics.ridge_cross_sectional.daily_cross_sectional_ic?.newey_west_hac_pvalue.toFixed(2)})
                </div>
              </div>

              {phase5jData.portfolio_simulation?.buy_and_hold_benchmark && (
                <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Equal-Weight Buy & Hold</div>
                  <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-green)' }}>
                    ${phase5jData.portfolio_simulation.buy_and_hold_benchmark.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                    Net: +{(phase5jData.portfolio_simulation.buy_and_hold_benchmark.total_net_return * 100).toFixed(1)}% | Max DD: {(phase5jData.portfolio_simulation.buy_and_hold_benchmark.max_drawdown * 100).toFixed(1)}%
                  </div>
                </div>
              )}

              {phase5jData.portfolio_simulation?.cross_sectional_policy && (
                <div style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Cross-Sectional Ridge Portfolio</div>
                  <div className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: phase5jData.portfolio_simulation.cross_sectional_policy.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    ${phase5jData.portfolio_simulation.cross_sectional_policy.final_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                    Net: +{(phase5jData.portfolio_simulation.cross_sectional_policy.total_net_return * 100).toFixed(2)}% | Win: {(phase5jData.portfolio_simulation.cross_sectional_policy.win_rate * 100).toFixed(1)}%
                  </div>
                </div>
              )}
            </div>

            {/* Multi-Track Comparison Table on Common Cohort */}
            {phase5jData.track_comparison && (
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Multi-Modal Track Comparison on Common Pilot Cohort (AAPL, JPM, GOOG, TSLA - N = 720)</span>
                  <span className="badge-tag badge-status">Strict Boundary</span>
                </div>
                <div className="terminal-table-wrapper">
                  <table className="terminal-table">
                    <thead>
                      <tr>
                        <th>Track</th>
                        <th>Features</th>
                        <th>N Obs</th>
                        <th>RMSE</th>
                        <th>MAE</th>
                        <th>Hit Rate</th>
                        <th>Rank IC</th>
                        <th>P-Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(phase5jData.track_comparison).map(([trackName, tData]) => (
                        <tr key={trackName}>
                          <td style={{ fontWeight: 600 }}>{trackName}</td>
                          <td style={{ color: 'var(--text-dim)' }}>
                            {trackName.includes('Combined') ? '28 feats' : trackName.includes('Events') ? '20 feats' : trackName.includes('Fundamentals') ? '25 feats' : '17 feats'}
                          </td>
                          <td className="font-mono">{tData.n_observations}</td>
                          <td className="font-mono">{(tData.rmse * 100).toFixed(2)}%</td>
                          <td className="font-mono">{(tData.mae * 100).toFixed(2)}%</td>
                          <td className="font-mono">{(tData.hit_rate * 100).toFixed(1)}%</td>
                          <td className="font-mono" style={{ color: tData.rank_ic > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                            {tData.rank_ic > 0 ? '+' : ''}{tData.rank_ic.toFixed(3)}
                          </td>
                          <td className="font-mono" style={{ color: tData.rank_ic_pvalue < 0.05 ? 'var(--accent-green)' : 'var(--text-dim)' }}>
                            {tData.rank_ic_pvalue.toExponential(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Fold Schedule Breakdown Table */}
            {phase5jData.fold_results && (
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Chronological Walk-Forward Folds (4 Outer Folds, 5-Session Purge Gap)</span>
                  <span className="badge-tag badge-experimental">Phase 5J Panel</span>
                </div>
                <div className="terminal-table-wrapper">
                  <table className="terminal-table">
                    <thead>
                      <tr>
                        <th>Fold</th>
                        <th>Validation Window</th>
                        <th>Train Obs</th>
                        <th>Val Obs</th>
                        <th>Companies</th>
                        <th>Zero RMSE</th>
                        <th>Ridge RMSE</th>
                        <th>Hit Rate</th>
                        <th>Daily IC</th>
                      </tr>
                    </thead>
                    <tbody>
                      {phase5jData.fold_results.map((f) => (
                        <tr key={f.fold}>
                          <td className="font-mono"><strong>Fold {f.fold}</strong></td>
                          <td className="font-mono">{f.val_start_date} → {f.val_end_date} {f.fold === 2 ? '(COVID-19 Crash)' : ''}</td>
                          <td className="font-mono">{f.n_train_obs.toLocaleString()}</td>
                          <td className="font-mono">{f.n_val_obs.toLocaleString()}</td>
                          <td className="font-mono">{f.n_val_companies} co</td>
                          <td className="font-mono">{(f.metrics.zero_baseline.rmse * 100).toFixed(2)}%</td>
                          <td className="font-mono" style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
                            {(f.metrics.ridge_cross_sectional.rmse * 100).toFixed(2)}%
                          </td>
                          <td className="font-mono">{(f.metrics.ridge_cross_sectional.hit_rate * 100).toFixed(1)}%</td>
                          <td className="font-mono" style={{ color: f.metrics.ridge_cross_sectional.ic > 0 ? 'var(--accent-green)' : 'var(--accent-amber)' }}>
                            {f.metrics.ridge_cross_sectional.ic > 0 ? '+' : ''}{f.metrics.ridge_cross_sectional.ic.toFixed(3)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            VIEW 3: PHASE 5K — SYSTEMATIC MODEL IMPROVEMENT (8 CANDIDATES)
            ========================================================================= */}
        {activeResearchPhase === 'phase5k' && phase5kData && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="card">
              <div className="card-header">
                <span className="card-title">Consolidated Out-of-Sample Performance Comparison (N = {phase5kData.metadata?.total_out_of_sample_observations?.toLocaleString() || '10,559'} Observations)</span>
                <span className="badge-tag badge-status">Pre-Specified 8 Hypotheses</span>
              </div>
              <div className="terminal-table-wrapper">
                <table className="terminal-table">
                  <thead>
                    <tr>
                      <th>Candidate Model / Hypothesis</th>
                      <th>Category</th>
                      <th>OOS RMSE</th>
                      <th>OOS MAE</th>
                      <th>Hit Rate</th>
                      <th>Daily CS IC</th>
                      <th>HAC P-Value</th>
                      <th>Sim Net Return</th>
                      <th>Max DD</th>
                      <th>Trades (Win %)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(phase5kData.aggregate_model_metrics).map(([modelId, mData]) => {
                      const sim = phase5kData.portfolio_simulation?.[modelId];
                      return (
                        <tr key={modelId}>
                          <td style={{ fontWeight: 600 }}>
                            <span className="font-mono">{modelId}</span>
                            <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 'normal' }}>
                              {mData.hypothesis_name}
                            </div>
                          </td>
                          <td>
                            <span className="badge-tag badge-experimental">{mData.category}</span>
                          </td>
                          <td className="font-mono">{(mData.rmse * 100).toFixed(2)}%</td>
                          <td className="font-mono">{(mData.mae * 100).toFixed(2)}%</td>
                          <td className="font-mono">{(mData.directional_hit_rate * 100).toFixed(1)}%</td>
                          <td className="font-mono" style={{ color: mData.daily_cross_sectional_ic?.mean_daily_ic > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                            {mData.daily_cross_sectional_ic?.mean_daily_ic > 0 ? '+' : ''}
                            {mData.daily_cross_sectional_ic?.mean_daily_ic ? mData.daily_cross_sectional_ic.mean_daily_ic.toFixed(3) : 'N/A'}
                          </td>
                          <td className="font-mono" style={{ color: mData.daily_cross_sectional_ic?.newey_west_hac_pvalue < 0.1 ? 'var(--accent-green)' : 'var(--text-dim)' }}>
                            {mData.daily_cross_sectional_ic?.newey_west_hac_pvalue ? mData.daily_cross_sectional_ic.newey_west_hac_pvalue.toFixed(2) : 'N/A'}
                          </td>
                          <td className="font-mono" style={{ color: sim && sim.total_net_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {sim ? `${sim.total_net_return >= 0 ? '+' : ''}${(sim.total_net_return * 100).toFixed(2)}%` : 'N/A'}
                          </td>
                          <td className="font-mono">
                            {sim ? `${(sim.max_drawdown * 100).toFixed(2)}%` : 'N/A'}
                          </td>
                          <td className="font-mono" style={{ fontSize: '11px' }}>
                            {sim ? `${sim.total_closed_trades} (${(sim.win_rate * 100).toFixed(1)}%)` : '0 trades'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            VIEW 4: PHASE 8 — FINANCIAL REPORTS SPECIALIST MODEL (305 COMPANIES)
            ========================================================================= */}
        {activeResearchPhase === 'phase8' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Scientific Finding & Governance Banner */}
            <div className="disclaimer-banner" style={{ borderLeftColor: 'var(--accent-red)', background: 'rgba(244, 63, 94, 0.06)' }}>
              <ShieldAlert size={20} style={{ color: 'var(--accent-red)', flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong style={{ color: 'var(--accent-red)', fontSize: '13px', letterSpacing: '0.3px' }}>
                  RESEARCH FINDING: STATISTICALLY NULL INCREMENTAL ALPHA (Holdout p = 0.3468)
                </strong>
                <p style={{ marginTop: '5px', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                  Phase 8 completed a rigorous like-for-like evaluation comparing the Market Baseline (<span className="font-mono">M_MKT</span>, 15 features),
                  the Financial Specialist (<span className="font-mono">M_FIN</span>, 15 features), and the Combined Model (<span className="font-mono">M_COMB</span>, 30 features).
                  Adding 15 point-in-time SEC XBRL financial features to 15 market features produced an incremental Information Coefficient delta of{' '}
                  <strong className="font-mono text-negative">ΔIC = -0.0043 (two-sided HAC t = -0.9417, p = 0.3468)</strong> in the independent 2022–2023 holdout.
                  The standalone financial specialist alone achieved <span className="font-mono">Mean IC = -0.0008 (HAC t = -0.1392, p = 0.8893)</span>.
                  Quarterly accounting facts provide <strong>zero statistically significant incremental predictive power</strong> over a 5-day horizon (fail to reject H₀).
                </p>
                <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--accent-amber)', lineHeight: '1.5' }}>
                  <strong>Governance Warning:</strong> Institutional economic simulation proves gross Sharpe ratios (0.16 to 0.67) are completely eliminated by portfolio turnover (118.4% two-way daily churn)
                  under realistic transaction friction (10–30 bps), resulting in net Sharpe ratios of <strong>-1.29 to -5.19</strong>.
                  These models are NOT profitable trading strategies and must not be used for live capital allocation.
                </div>
              </div>
            </div>

            {/* Model Architecture Specifications Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '14px' }}>
              <div className="card" style={{ borderTop: '3px solid var(--accent-blue)', background: 'var(--bg-card)' }}>
                <div className="card-header" style={{ paddingBottom: '10px' }}>
                  <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers size={15} style={{ color: 'var(--accent-blue)' }} />
                    <span style={{ color: 'var(--text-primary)' }}>M_MKT: Market Baseline</span>
                  </span>
                  <span className="badge-tag badge-status">15 Features</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                  <div><strong style={{ color: 'var(--text-primary)' }}>Features:</strong> 1d/5d/21d returns, 5d/21d/63d volatility, momentum, SMA distances, z-scores, RSI, volume ratios.</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Estimator:</strong> L2 Ridge Regression (α = 1000.0, sector-neutral).</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Target:</strong> 5-day sector-neutral excess return (<span className="font-mono">target_sec_excess</span>).</div>
                </div>
              </div>

              <div className="card" style={{ borderTop: '3px solid var(--accent-cyan)', background: 'var(--bg-card)' }}>
                <div className="card-header" style={{ paddingBottom: '10px' }}>
                  <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Database size={15} style={{ color: 'var(--accent-cyan)' }} />
                    <span style={{ color: 'var(--text-primary)' }}>M_FIN: Financial Specialist</span>
                  </span>
                  <span className="badge-tag badge-experimental">15 Features</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                  <div><strong style={{ color: 'var(--text-primary)' }}>Features:</strong> Margins, ROA, ROE, debt-to-assets, debt-to-equity, current ratio, cash flows, Sloan accruals, filing age.</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Estimator:</strong> L2 Ridge Regression (α = 1000.0, sector-neutral).</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Target:</strong> 5-day sector-neutral excess return (<span className="font-mono">target_sec_excess</span>).</div>
                </div>
              </div>

              <div className="card" style={{ borderTop: '3px solid var(--accent-purple, #a855f7)', background: 'var(--bg-card)' }}>
                <div className="card-header" style={{ paddingBottom: '10px' }}>
                  <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers size={15} style={{ color: 'var(--accent-purple, #a855f7)' }} />
                    <span style={{ color: 'var(--text-primary)' }}>M_COMB: Combined Model</span>
                  </span>
                  <span className="badge-tag" style={{ background: 'rgba(168, 85, 247, 0.12)', color: 'var(--accent-purple)', border: '1px solid rgba(168, 85, 247, 0.3)' }}>30 Features</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                  <div><strong style={{ color: 'var(--text-primary)' }}>Features:</strong> Full concatenation of 15 Market + 15 Point-in-Time Financial features.</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Estimator:</strong> L2 Ridge Regression (α = 1000.0, sector-neutral).</div>
                  <div style={{ marginTop: '6px' }}><strong style={{ color: 'var(--text-primary)' }}>Target:</strong> 5-day sector-neutral excess return (<span className="font-mono">target_sec_excess</span>).</div>
                </div>
              </div>
            </div>

            {/* Independent Final Holdout Results (2022-2023) */}
            <div className="card">
              <div className="card-header" style={{ flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Award size={16} style={{ color: 'var(--accent-blue)' }} />
                  <span>Independent Holdout Evaluation (2022–2023)</span>
                </span>
                <div className="meta-chip-group">
                  <div className="meta-chip">
                    <span className="meta-chip-label">Window:</span>
                    <span className="meta-chip-value">2022-01-10 → 2023-12-20</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Rows:</span>
                    <span className="meta-chip-value">113,549 obs</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Universe:</span>
                    <span className="meta-chip-value">234 Tickers</span>
                  </div>
                  <span className="badge-tag badge-experimental font-mono" title="Reused historical holdout from earlier research phases; serves as benchmark rather than unseen blind holdout">
                    Reused Historical Holdout
                  </span>
                </div>
              </div>

              <div className="data-table-container">
                <table className="data-table" style={{ minWidth: '1020px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '230px' }}>Model Architecture</th>
                      <th style={{ width: '170px' }}>Feature Set</th>
                      <th className="num-col" style={{ width: '105px' }}>Mean Daily IC</th>
                      <th className="num-col" style={{ width: '105px' }}>Median Daily IC</th>
                      <th className="num-col" style={{ width: '90px' }}>% Pos Days</th>
                      <th className="num-col" style={{ width: '95px' }}>HAC SE (L=4)</th>
                      <th className="num-col" style={{ width: '90px' }}>HAC t-stat</th>
                      <th className="num-col" style={{ width: '105px' }}>HAC p-value</th>
                      <th className="num-col" style={{ width: '80px' }}>Hit Rate</th>
                      <th className="num-col" style={{ width: '75px' }}>MAE</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="font-mono">M_MKT</span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>(Market-Only)</span>
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Frozen M4 Ridge Regression</div>
                      </td>
                      <td>
                        <span className="badge-tag badge-status">15 Market Features</span>
                      </td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>+0.0248</td>
                      <td className="num-col">+0.0207</td>
                      <td className="num-col">56.5%</td>
                      <td className="num-col">0.0089</td>
                      <td className="num-col text-positive">+2.783</td>
                      <td className="num-col" style={{ color: 'var(--accent-green)', fontWeight: 600 }}>0.0056</td>
                      <td className="num-col">50.8%</td>
                      <td className="num-col">4.88%</td>
                    </tr>
                    <tr>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="font-mono">M_FIN</span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>(Financial Specialist)</span>
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Quarterly Fundamental Ridge</div>
                      </td>
                      <td>
                        <span className="badge-tag badge-experimental">15 Point-in-Time XBRL</span>
                      </td>
                      <td className="num-col">+0.0076</td>
                      <td className="num-col">+0.0069</td>
                      <td className="num-col">53.7%</td>
                      <td className="num-col">0.0075</td>
                      <td className="num-col">+1.018</td>
                      <td className="num-col" style={{ color: 'var(--text-muted)' }}>0.3092</td>
                      <td className="num-col">50.3%</td>
                      <td className="num-col">4.89%</td>
                    </tr>
                    <tr>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--accent-purple)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="font-mono">M_COMB</span>
                          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>(Market + Financials)</span>
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Combined Concatenated Ridge</div>
                      </td>
                      <td>
                        <span className="badge-tag" style={{ background: 'rgba(168, 85, 247, 0.12)', color: 'var(--accent-purple)', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
                          30 Features
                        </span>
                      </td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>+0.0205</td>
                      <td className="num-col">+0.0227</td>
                      <td className="num-col">56.1%</td>
                      <td className="num-col">0.0088</td>
                      <td className="num-col text-positive">+2.340</td>
                      <td className="num-col" style={{ color: 'var(--accent-green)', fontWeight: 600 }}>0.0197</td>
                      <td className="num-col">50.8%</td>
                      <td className="num-col">4.88%</td>
                    </tr>
                    <tr className="delta-row">
                      <td>
                        <div style={{ color: 'var(--accent-amber)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>Incremental Delta</span>
                          <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>(M_COMB − M_MKT)</span>
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>Net Financial Contribution</div>
                      </td>
                      <td>
                        <span className="badge-tag badge-offline" style={{ fontSize: '10px' }}>Alpha Differential</span>
                      </td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-0.0043</td>
                      <td className="num-col">+0.0020</td>
                      <td className="num-col">51.6%</td>
                      <td className="num-col">0.0046</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-0.9417</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>
                        <span>0.3468</span>
                        <span style={{ marginLeft: '4px', fontSize: '10px', opacity: 0.85 }}>(Fail)</span>
                      </td>
                      <td className="num-col">0.0%</td>
                      <td className="num-col">0.00%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                <span>* Newey-West HAC adjustments use lag length L=4. Incremental delta p-value (p = 0.3468, t = -0.9417) fails two-sided significance; standalone financial specialist holdout test yields p = 0.8893 (t = -0.1392).</span>
                <span style={{ color: 'var(--accent-amber)' }}>Warning: Reused historical holdout evaluated for verification only.</span>
              </div>
            </div>

            {/* 4-Fold Walk-Forward Cross-Validation (2020-2021) */}
            <div className="card">
              <div className="card-header" style={{ flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={16} style={{ color: 'var(--accent-blue)' }} />
                  <span>4-Fold Walk-Forward Cross-Validation (2020–2021)</span>
                </span>
                <div className="meta-chip-group">
                  <div className="meta-chip">
                    <span className="meta-chip-label">Window:</span>
                    <span className="meta-chip-value">2020-01-08 → 2021-12-31</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Dev Obs:</span>
                    <span className="meta-chip-value">117,988 rows</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Universe:</span>
                    <span className="meta-chip-value">290 Tickers</span>
                  </div>
                  <span className="badge-tag badge-status font-mono">Development Panel</span>
                </div>
              </div>

              <div className="data-table-container">
                <table className="data-table" style={{ minWidth: '940px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '85px' }}>Fold</th>
                      <th style={{ width: '220px' }}>Validation Window</th>
                      <th className="num-col" style={{ width: '130px' }}>Validation Rows</th>
                      <th className="num-col" style={{ width: '115px' }}>M_MKT IC</th>
                      <th className="num-col" style={{ width: '115px' }}>M_FIN IC</th>
                      <th className="num-col" style={{ width: '115px' }}>M_COMB IC</th>
                      <th className="num-col" style={{ width: '160px' }}>ΔIC (COMB − MKT)</th>
                      <th className="center-col" style={{ width: '120px' }}>Fold Winner</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="font-mono" style={{ fontWeight: 600 }}>Fold 0</td>
                      <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>2020-01-08 → 2020-07-06</td>
                      <td className="num-col">29,484</td>
                      <td className="num-col">+0.0135</td>
                      <td className="num-col">+0.0052</td>
                      <td className="num-col">+0.0088</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-0.0047</td>
                      <td className="center-col"><span className="badge-tag badge-status">M_MKT</span></td>
                    </tr>
                    <tr>
                      <td className="font-mono" style={{ fontWeight: 600 }}>Fold 1</td>
                      <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>2020-07-07 → 2020-12-31</td>
                      <td className="num-col">31,048</td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>+0.0464</td>
                      <td className="num-col">+0.0143</td>
                      <td className="num-col">+0.0382</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-0.0082</td>
                      <td className="center-col"><span className="badge-tag badge-status">M_MKT</span></td>
                    </tr>
                    <tr>
                      <td className="font-mono" style={{ fontWeight: 600 }}>Fold 2</td>
                      <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>2021-01-04 → 2021-07-01</td>
                      <td className="num-col">29,788</td>
                      <td className="num-col">+0.0270</td>
                      <td className="num-col text-negative">-0.0045</td>
                      <td className="num-col">+0.0125</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-0.0145</td>
                      <td className="center-col"><span className="badge-tag badge-status">M_MKT</span></td>
                    </tr>
                    <tr>
                      <td className="font-mono" style={{ fontWeight: 600 }}>Fold 3</td>
                      <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>2021-07-02 → 2021-12-31</td>
                      <td className="num-col">27,668</td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>+0.0617</td>
                      <td className="num-col">+0.0210</td>
                      <td className="num-col">+0.0270</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-0.0347</td>
                      <td className="center-col"><span className="badge-tag badge-status">M_MKT</span></td>
                    </tr>
                    <tr className="summary-row">
                      <td colSpan={2} style={{ fontWeight: 700 }}>Average Walk-Forward Development Performance</td>
                      <td className="num-col" style={{ fontWeight: 600 }}>117,988 Total</td>
                      <td className="num-col text-positive" style={{ fontWeight: 700 }}>+0.0372</td>
                      <td className="num-col">+0.0090</td>
                      <td className="num-col">+0.0216</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-0.0155 (p = 0.0065)</td>
                      <td className="center-col"><span className="badge-tag badge-status" style={{ fontWeight: 700 }}>M_MKT (4/4)</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Economic Simulation & Friction Realism (Phase 8R.1 Verified) */}
            <div className="card">
              <div className="card-header" style={{ flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <TrendingDown size={16} style={{ color: 'var(--accent-red)' }} />
                  <span>Institutional Economic Simulation & Transaction Friction (Holdout 2022–2023)</span>
                </span>
                <div className="meta-chip-group">
                  <div className="meta-chip">
                    <span className="meta-chip-label">Strategy:</span>
                    <span className="meta-chip-value">Q5 Long / Q1 Short Quintile</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Sessions:</span>
                    <span className="meta-chip-value">490 Trading Days</span>
                  </div>
                  <span className="badge-tag badge-status font-mono">Phase 8R.1 Audited</span>
                </div>
              </div>

              <div style={{ padding: '2px 0 12px', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                Market-neutral top vs bottom quintile portfolio strategy. All metrics verified using Newey-West HAC calculations with 4-lag autocorrelation adjustments.
              </div>

              <div className="data-table-container">
                <table className="data-table" style={{ minWidth: '960px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '230px' }}>Strategy / Metric</th>
                      <th className="num-col" style={{ width: '135px' }}>M_MKT Baseline</th>
                      <th className="num-col" style={{ width: '135px' }}>M_FIN Specialist</th>
                      <th className="num-col" style={{ width: '135px' }}>M_COMB Combined</th>
                      <th style={{ minWidth: '320px' }}>Economic Interpretation & Risk Reality</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="group-header-row">
                      <td colSpan={5}>Tier 1: Pre-Friction Gross Simulation (Theoretical Benchmark)</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Cumulative Gross Return</td>
                      <td className="num-col text-positive">+5.49%</td>
                      <td className="num-col">+1.27%</td>
                      <td className="num-col text-positive">+6.64%</td>
                      <td>Combined model produces marginally higher gross return before trading fees.</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Annualized Gross Return</td>
                      <td className="num-col">+2.84%</td>
                      <td className="num-col">+0.65%</td>
                      <td className="num-col">+3.44%</td>
                      <td>Modest gross annualized alpha; insufficient to withstand real-world frictions.</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Annualized Volatility</td>
                      <td className="num-col">4.82%</td>
                      <td className="num-col">4.06%</td>
                      <td className="num-col">5.17%</td>
                      <td>Market-neutral quintile portfolio variance is stable across all candidates.</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Gross Sharpe Ratio</td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>0.589</td>
                      <td className="num-col">0.160</td>
                      <td className="num-col text-positive" style={{ fontWeight: 600 }}>0.666</td>
                      <td>Gross Sharpe appears positive prior to friction deduction.</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Two-Way Empirical Turnover</td>
                      <td className="num-col" style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>119.2% / session</td>
                      <td className="num-col" style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>84.7% / session</td>
                      <td className="num-col" style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>118.4% / session</td>
                      <td style={{ color: 'var(--accent-amber)' }}>Rapid rank churn creates massive daily turnover that eliminates gross profits.</td>
                    </tr>

                    <tr className="group-header-row">
                      <td colSpan={5}>Tier 2: Institutional Cost Scenarios (Post-Friction Net Performance)</td>
                    </tr>
                    <tr style={{ background: 'rgba(244, 63, 94, 0.04)' }}>
                      <td style={{ fontWeight: 600, color: 'var(--accent-red)' }}>Net Sharpe @ 10 bps Friction</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-2.35</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-1.48</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-2.22</td>
                      <td style={{ color: 'var(--accent-red)' }}>Severely negative net Sharpe even under ultra-tight institutional execution costs.</td>
                    </tr>
                    <tr style={{ background: 'rgba(244, 63, 94, 0.07)' }}>
                      <td style={{ fontWeight: 600, color: 'var(--accent-red)' }}>Net Sharpe @ 20 bps Friction</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-5.33</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-3.12</td>
                      <td className="num-col text-negative" style={{ fontWeight: 600 }}>-5.11</td>
                      <td style={{ color: 'var(--accent-red)' }}>Catastrophic capital decay under realistic institutional prime-brokerage rates.</td>
                    </tr>
                    <tr style={{ background: 'rgba(244, 63, 94, 0.10)' }}>
                      <td style={{ fontWeight: 600, color: 'var(--accent-red)' }}>Net Sharpe @ 30 bps Friction</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-8.30</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-4.76</td>
                      <td className="num-col text-negative" style={{ fontWeight: 700 }}>-8.00</td>
                      <td style={{ color: 'var(--accent-red)' }}>Complete capital loss; proves absolute non-viability as a live trading system.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* 15 Point-in-Time Financial Feature Catalog */}
            <div className="card">
              <div className="card-header" style={{ flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                <span className="card-title" style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Database size={16} style={{ color: 'var(--accent-cyan)' }} />
                  <span>Phase 8 Point-in-Time Financial Feature Catalog (15 Features)</span>
                </span>
                <div className="meta-chip-group">
                  <div className="meta-chip">
                    <span className="meta-chip-label">Source:</span>
                    <span className="meta-chip-value">SEC EDGAR Submissions API</span>
                  </div>
                  <div className="meta-chip">
                    <span className="meta-chip-label">Safeguard:</span>
                    <span className="meta-chip-value">Filing Time &lt; Market Close</span>
                  </div>
                  <span className="badge-tag badge-status font-mono">Zero Lookahead Guaranteed</span>
                </div>
              </div>

              <div className="data-table-container">
                <table className="data-table" style={{ minWidth: '1020px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '220px' }}>Feature Identifier</th>
                      <th style={{ width: '160px' }}>Category</th>
                      <th style={{ width: '300px' }}>Formal Definition / Accounting Formula</th>
                      <th style={{ minWidth: '340px' }}>Point-in-Time Safety &amp; Staleness Policy</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><span className="feature-tag">fin_gross_margin</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(16, 185, 129, 0.12)', color: 'var(--accent-green)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                          Profitability
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Gross Profit / Total Revenue</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Available strictly after SEC EDGAR acceptance timestamp.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_operating_margin</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(16, 185, 129, 0.12)', color: 'var(--accent-green)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                          Profitability
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Operating Income / Total Revenue</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Available strictly after SEC EDGAR acceptance timestamp.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_net_margin</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(16, 185, 129, 0.12)', color: 'var(--accent-green)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                          Profitability
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Net Income / Total Revenue</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Available strictly after SEC EDGAR acceptance timestamp.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_roa</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(6, 182, 212, 0.12)', color: 'var(--accent-cyan)', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
                          Return Quality
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Net Income / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Preserves original filing date; restatements strictly isolated.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_roe</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(6, 182, 212, 0.12)', color: 'var(--accent-cyan)', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
                          Return Quality
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Net Income / Stockholders' Equity</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Preserves original filing date; restatements strictly isolated.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_debt_to_assets</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(245, 158, 11, 0.12)', color: 'var(--accent-amber)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                          Leverage
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Total Debt / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>180-day max staleness safeguard; imputed as NaN if older.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_debt_to_equity</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(245, 158, 11, 0.12)', color: 'var(--accent-amber)', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                          Leverage
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Total Debt / Stockholders' Equity</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>180-day max staleness safeguard; imputed as NaN if older.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_current_ratio</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(59, 130, 246, 0.12)', color: 'var(--accent-blue)', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
                          Liquidity
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Current Assets / Current Liabilities</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Point-in-time balance sheet facts from primary 10-Q/10-K.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_cash_to_assets</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(59, 130, 246, 0.12)', color: 'var(--accent-blue)', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
                          Liquidity
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Cash &amp; Equivalents / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Point-in-time balance sheet facts from primary 10-Q/10-K.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_ocf_to_assets</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(168, 85, 247, 0.12)', color: 'var(--accent-purple)', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
                          Cash Flow
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Operating Cash Flow / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Point-in-time statement of cash flows facts.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_fcf_to_assets</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(168, 85, 247, 0.12)', color: 'var(--accent-purple)', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
                          Cash Flow
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Free Cash Flow (OCF − Capex) / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Point-in-time cash flow facts; capex deducted.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_ocf_to_net_income</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(236, 72, 153, 0.12)', color: '#ec4899', border: '1px solid rgba(236, 72, 153, 0.3)' }}>
                          Earnings Quality
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Operating Cash Flow / Net Income</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Earnings quality &amp; cash conversion ratio diagnostic.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_accruals</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(236, 72, 153, 0.12)', color: '#ec4899', border: '1px solid rgba(236, 72, 153, 0.3)' }}>
                          Earnings Quality
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Sloan Accruals / Total Assets</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Measures non-cash accounting accrual intensity.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_earnings_yield</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(99, 102, 241, 0.12)', color: '#818cf8', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                          Valuation
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Operating Income / Market Capitalization</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Combined with session T closing market equity.</td>
                    </tr>
                    <tr>
                      <td><span className="feature-tag">fin_filing_age_days</span></td>
                      <td>
                        <span className="category-pill" style={{ background: 'rgba(148, 163, 184, 0.15)', color: 'var(--text-secondary)', border: '1px solid rgba(148, 163, 184, 0.3)' }}>
                          Staleness Diagnostic
                        </span>
                      </td>
                      <td className="font-mono" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Elapsed calendar days since SEC acceptance</td>
                      <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Diagnostic tracking elapsed point-in-time information decay.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
