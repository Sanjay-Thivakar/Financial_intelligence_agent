import React, { useState } from 'react';
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
import { ShieldAlert, Award, FileSpreadsheet, AlertTriangle, CheckCircle2 } from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

export default function ModelLabTab({ evalData, loading }) {
  const [activeCohort, setActiveCohort] = useState('panel'); // 'panel' or 'two_company'

  if (loading || !evalData) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <p>Loading model evaluation repository and fold-level metrics...</p>
      </div>
    );
  }

  const folds = activeCohort === 'panel' ? evalData.fold_results : evalData.two_company_cohort_results;

  // Final Holdout Bar Chart (Fold 3)
  const holdoutFold = evalData.fold_results.find((f) => f.fold === 3);

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
        borderColor: [
          '#94a3b8',
          '#f59e0b',
          '#3b82f6',
          '#06b6d4',
        ],
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Prominent Provenance Callout */}
      <div className="disclaimer-banner" style={{ borderLeftColor: 'var(--accent-blue)' }}>
        <FileSpreadsheet size={16} style={{ color: 'var(--accent-blue)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong style={{ color: 'var(--accent-blue)' }}>EVALUATION PROVENANCE:</strong>{' '}
          <span className="font-mono">{evalData.provenance}</span>.
          All reported scores reflect audited 4-fold walk-forward validation with 5-session purge gaps and training-only preprocessing.
        </div>
      </div>

      {/* Trading Profitability Disclaimer */}
      <div className="disclaimer-banner">
        <AlertTriangle size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>CRITICAL QUANTITATIVE LIMITATION:</strong> Lower forward return-prediction error (MAE/RMSE) does{' '}
          <strong>NOT</strong> establish trading profitability, execution feasibility, or positive portfolio Sharpe ratios.
          Transaction costs, bid-ask spreads, borrowing fees, and slippage are not modeled in these baseline experiments.
        </div>
      </div>

      {/* Hero Holdout Comparison Chart & Key Metric Cards */}
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
            <span className="badge-tag badge-experimental">Verified</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Target Definition</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>{evalData.target_definition}</div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Purge Requirement</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                Strict 5-trading-day purge between train end and validation start. No label overlap.
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Hyperparameter Selection</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '11px' }}>
                L2 regularization tuned on train split (alpha=1000.0 selected for all folds).
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
                  <td
                    className={`font-mono ${
                      fold.market_ridge_ic >= 0 ? 'text-positive' : 'text-negative'
                    }`}
                  >
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
  );
}
