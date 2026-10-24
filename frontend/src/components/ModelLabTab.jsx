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
} from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

export default function ModelLabTab({ evalData, loading, selectedTicker, companyMeta }) {
  const [activeResearchPhase, setActiveResearchPhase] = useState('phase5d'); // 'phase5d', 'phase5j', 'phase5k'
  const [activeCohort, setActiveCohort] = useState('panel'); // for Phase 5D: 'panel' or 'two_company'
  const [phase5jData, setPhase5jData] = useState(null);
  const [phase5kData, setPhase5kData] = useState(null);

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
              : 'Phase 5K Systematic Model Improvement Report (docs/phase5k_model_improvement_report.md)'}
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
      </div>
    </div>
  );
}
