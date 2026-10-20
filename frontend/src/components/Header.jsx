import React from 'react';
import { Activity, ShieldAlert, Cpu, Database, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Header({
  activeTab,
  setActiveTab,
  companies,
  selectedTicker,
  setSelectedTicker,
  apiConnected,
}) {
  return (
    <>
      <header className="terminal-header">
        <div className="header-left">
          <div className="brand-title">
            <span className="brand-dot"></span>
            <span>Financial Intelligence Agent</span>
          </div>
          <span className="badge-tag badge-experimental">
            Research / Experimental
          </span>
          <span className={`badge-tag ${apiConnected ? 'badge-status' : 'badge-offline'}`}>
            {apiConnected ? (
              <>
                <CheckCircle2 size={12} />
                <span>API Connected</span>
              </>
            ) : (
              <>
                <AlertCircle size={12} />
                <span>API Offline</span>
              </>
            )}
          </span>
        </div>

        <nav className="header-nav">
          <button
            className={`nav-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
            id="nav-tab-overview"
          >
            <Activity size={14} />
            <span>Overview</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'charts' ? 'active' : ''}`}
            onClick={() => setActiveTab('charts')}
            id="nav-tab-charts"
          >
            <Activity size={14} />
            <span>Market Charts</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'models' ? 'active' : ''}`}
            onClick={() => setActiveTab('models')}
            id="nav-tab-models"
          >
            <Cpu size={14} />
            <span>Model Lab</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'prediction' ? 'active' : ''}`}
            onClick={() => setActiveTab('prediction')}
            id="nav-tab-prediction"
          >
            <ShieldAlert size={14} />
            <span>Prediction Research</span>
          </button>
          <button
            className={`nav-tab-btn ${activeTab === 'explorer' ? 'active' : ''}`}
            onClick={() => setActiveTab('explorer')}
            id="nav-tab-explorer"
          >
            <Database size={14} />
            <span>60-Company Screener</span>
          </button>
        </nav>
      </header>

      <div className="terminal-subbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
            Eligible Universe:
          </span>
          <div className="company-pills">
            {companies.map((comp) => (
              <button
                key={comp.ticker}
                className={`company-pill ${selectedTicker === comp.ticker ? 'active' : ''}`}
                onClick={() => setSelectedTicker(comp.ticker)}
                id={`pill-ticker-${comp.ticker}`}
              >
                <span>{comp.ticker}</span>
                <span style={{ opacity: 0.6, fontSize: '10px' }}>({comp.sector.split(' ')[0]})</span>
              </button>
            ))}
            <button
              className="company-pill company-pill-excluded"
              title="AA is excluded: Historical identity unresolved (2016 split into ARNC & AA)"
              disabled
              id="pill-ticker-AA-excluded"
            >
              <span>AA (Excluded)</span>
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px' }}>
          <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
            Active: <strong style={{ color: 'var(--accent-blue)' }}>{selectedTicker}</strong>
          </span>
          <span style={{ color: 'var(--border-medium)' }}>|</span>
          <span style={{ color: 'var(--text-dim)' }}>
            Purge Window: <strong>5 Sessions</strong>
          </span>
          <span style={{ color: 'var(--border-medium)' }}>|</span>
          <span style={{ color: 'var(--text-dim)' }}>
            Target: <strong>T+1 Open → T+5 Close</strong>
          </span>
        </div>
      </div>
    </>
  );
}
