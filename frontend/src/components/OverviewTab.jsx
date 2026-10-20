import React from 'react';
import {
  TrendingUp,
  Database,
  Calendar,
  FileText,
  Newspaper,
  Layers,
  AlertTriangle,
  CheckCircle,
  XCircle,
  HelpCircle,
} from 'lucide-react';

export default function OverviewTab({ companyMeta, marketData, loading, onNavigateToCharts }) {
  if (loading || !companyMeta) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <p>Loading company overview and historical market state...</p>
      </div>
    );
  }

  const latestPt =
    marketData && marketData.series && marketData.series.length > 0
      ? marketData.series[marketData.series.length - 1]
      : null;

  const return1d = latestPt && latestPt.market_return_1d !== null ? latestPt.market_return_1d * 100 : null;
  const return5d = latestPt && latestPt.market_return_5d !== null ? latestPt.market_return_5d * 100 : null;
  const vol21d = latestPt && latestPt.market_volatility_21d !== null ? latestPt.market_volatility_21d * 100 : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Non-Live Data Integrity Disclaimer */}
      <div className="disclaimer-banner">
        <AlertTriangle size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>HISTORICAL RESEARCH REPOSITORY:</strong> All observations reflect static historical market quotes and SEC filings from the verified prototype database. Observations are never labeled as live, and no external paid APIs or simulated real-time data feeds are invoked.
        </div>
      </div>

      {/* Hero Metric Grid */}
      <div className="metric-grid">
        <div className="metric-box">
          <span className="metric-label">Latest Session Close</span>
          <span className="metric-value">
            {latestPt ? `$${latestPt.adjusted_close.toFixed(2)}` : 'N/A'}
          </span>
          <span className="metric-sub">
            Date: {latestPt ? latestPt.trading_date : 'N/A'} (Historical)
          </span>
        </div>

        <div className="metric-box">
          <span className="metric-label">1-Day Session Return</span>
          <span
            className={`metric-value ${
              return1d === null ? '' : return1d >= 0 ? 'text-positive' : 'text-negative'
            }`}
          >
            {return1d !== null ? `${return1d >= 0 ? '+' : ''}${return1d.toFixed(2)}%` : 'N/A'}
          </span>
          <span className="metric-sub">Based on Adjusted Close</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">5-Day Cumulative Return</span>
          <span
            className={`metric-value ${
              return5d === null ? '' : return5d >= 0 ? 'text-positive' : 'text-negative'
            }`}
          >
            {return5d !== null ? `${return5d >= 0 ? '+' : ''}${return5d.toFixed(2)}%` : 'N/A'}
          </span>
          <span className="metric-sub">Price action lookback</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">21-Day Volatility (Ann.)</span>
          <span className="metric-value font-mono">
            {vol21d !== null ? `${vol21d.toFixed(1)}%` : 'N/A'}
          </span>
          <span className="metric-sub">Square-root-252 scaled</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">RSI (14-Day)</span>
          <span className="metric-value font-mono">
            {latestPt && latestPt.market_rsi_14d !== null ? latestPt.market_rsi_14d.toFixed(1) : 'N/A'}
          </span>
          <span className="metric-sub">Momentum oscillator</span>
        </div>
      </div>

      {/* Two Column Layout: Company Profile & Source Coverage Matrix */}
      <div className="terminal-grid">
        {/* Company Profile Card */}
        <div className="card" style={{ gridColumn: 'span 6' }}>
          <div className="card-header">
            <span className="card-title">
              <Database size={14} />
              <span>Company Entity Verification</span>
            </span>
            <span className="badge-tag badge-status">Verified CIK</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Entity Legal Name</span>
              <strong style={{ color: 'var(--text-primary)' }}>{companyMeta.company_name}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Ticker & Internal ID</span>
              <span className="font-mono">{companyMeta.ticker} / {companyMeta.company_id}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>SEC Central Index Key (CIK)</span>
              <span className="font-mono">{companyMeta.cik}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>GICS Economic Sector</span>
              <span>{companyMeta.sector}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>S&P 500 Index Interval</span>
              <span className="font-mono" style={{ fontSize: '11px' }}>{companyMeta.membership_interval}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: '2px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Historical Data Bounds</span>
              <span className="font-mono" style={{ color: 'var(--accent-blue)' }}>
                {companyMeta.min_date} → {companyMeta.max_date} ({companyMeta.total_sessions.toLocaleString()} sessions)
              </span>
            </div>
          </div>
        </div>

        {/* Multi-Layer Data Coverage Card */}
        <div className="card" style={{ gridColumn: 'span 6' }}>
          <div className="card-header">
            <span className="card-title">
              <Layers size={14} />
              <span>Three-Layer Information Architecture</span>
            </span>
            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
              Point-in-Time Status
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Layer 1: Market Data */}
            <div
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <TrendingUp size={16} style={{ color: 'var(--accent-blue)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Layer 1: Market Quotes & Features</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Daily OHLCV, split/dividend adjusted prices, 17 technical indicators
                  </div>
                </div>
              </div>
              <span className="badge-tag badge-status">Active (100%)</span>
            </div>

            {/* Layer 2: SEC Fundamentals */}
            <div
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <FileText size={16} style={{ color: 'var(--accent-cyan)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Layer 2: SEC EDGAR Financial Facts</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    Point-in-time filing acceptances, restatement isolation, financial ratios
                  </div>
                </div>
              </div>
              {companyMeta.sec_coverage_status === 'active_with_facts' ? (
                <span className="badge-tag badge-status">Active with Facts</span>
              ) : (
                <span className="badge-tag badge-offline" title="Preserved strictly as NaN; zero fabrication">
                  Unavailable (NaN)
                </span>
              )}
            </div>

            {/* Layer 3: Financial News */}
            <div
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Newspaper size={16} style={{ color: 'var(--accent-purple)' }} />
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Layer 3: Financial News & Events</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    FNSPID headlines sample (Phase 5E audit compliant, no text body)
                  </div>
                </div>
              </div>
              {companyMeta.news_coverage_status === 'active_with_headlines' ? (
                <span className="badge-tag badge-status">441 Headlines</span>
              ) : (
                <span className="badge-tag badge-offline">Unavailable in Pilot</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Target Engineering & Evaluation Architecture Summary */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Walk-Forward Target Definition & Experimental Protocol</span>
          <button className="chart-toggle-btn active" onClick={onNavigateToCharts}>
            Open Interactive Charts →
          </button>
        </div>

        <div className="terminal-grid" style={{ gap: '12px' }}>
          <div style={{ gridColumn: 'span 4', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
              Target Definition (y_T^(5)):
            </div>
            <p>
              Decision at session <strong style={{ color: '#fff' }}>T close</strong>, executable entry at <strong style={{ color: '#fff' }}>T+1 open</strong>, and exit at <strong style={{ color: '#fff' }}>T+5 close</strong>. Calculated using verified split/dividend adjusted opening and closing ratios.
            </p>
          </div>

          <div style={{ gridColumn: 'span 4', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
              5-Session Purge Invariant:
            </div>
            <p>
              Walk-forward evaluation enforces an exact <strong style={{ color: '#fff' }}>5-trading-day purge gap</strong> between training end and validation start to ensure training label holding periods never overlap validation decision points.
            </p>
          </div>

          <div style={{ gridColumn: 'span 4', fontSize: '12px', color: 'var(--text-secondary)' }}>
            <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
              Preprocessing Isolation:
            </div>
            <p>
              Imputation and feature scaling are fit strictly on training splits. Testing and holdout splits are never touched prior to evaluation. Missing fundamentals are left as unobserved <strong style={{ color: 'var(--accent-amber)' }}>NaN</strong>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
