import React from 'react';
import { Activity, ShieldAlert, Cpu, Database, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Header({
  activeTab,
  setActiveTab,
  companies = [],
  selectedTicker,
  setSelectedTicker,
  apiConnected,
  capabilitiesLoading,
  capabilitiesError,
  _excludedEntities = [],
  activeCompanyMeta,
}) {
  const isPrototypeSelected = ['AAPL', 'JPM', 'GOOG', 'TSLA'].includes(selectedTicker);
  const prototypeCompanies = companies.filter((c) => ['AAPL', 'JPM', 'GOOG', 'TSLA'].includes(c.ticker));
  const expandedCompanies = companies.filter((c) => !['AAPL', 'JPM', 'GOOG', 'TSLA'].includes(c.ticker));

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
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>
            Eligible Universe:
          </span>

          {/* Quick-Access Prototype Pills */}
          <div className="company-pills">
            {prototypeCompanies.map((comp) => (
              <button
                key={comp.ticker}
                className={`company-pill ${selectedTicker === comp.ticker ? 'active' : ''}`}
                onClick={() => setSelectedTicker(comp.ticker)}
                id={`pill-ticker-${comp.ticker}`}
                title={`${comp.company_name} (${comp.sector})`}
              >
                <span>{comp.ticker}</span>
                <span style={{ opacity: 0.6, fontSize: '10px' }}>
                  ({comp.sector ? comp.sector.split(' ')[0] : 'Pilot'})
                </span>
              </button>
            ))}

            {/* Active Expanded Cohort Pill if currently selected */}
            {!isPrototypeSelected && selectedTicker && (
              <button
                key={selectedTicker}
                className="company-pill active"
                id={`pill-ticker-${selectedTicker}`}
                title={activeCompanyMeta?.company_name || selectedTicker}
              >
                <span>{selectedTicker}</span>
                <span style={{ opacity: 0.6, fontSize: '10px' }}>
                  ({activeCompanyMeta?.sector ? activeCompanyMeta.sector.split(' ')[0] : 'Cohort'})
                </span>
              </button>
            )}

            {/* Excluded Entity Guardrail Pill */}
            <button
              className="company-pill company-pill-excluded"
              title="AA is excluded: Historical identity unresolved (2016 split into ARNC & AA)"
              disabled
              id="pill-ticker-AA-excluded"
            >
              <span>AA (Excluded)</span>
            </button>
          </div>

          {/* 60-Company Capability Universe Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <select
              className="company-select-dropdown"
              value={selectedTicker}
              onChange={(e) => setSelectedTicker(e.target.value)}
              id="select-company-universe"
              aria-label="Select company from 60-company research universe"
              disabled={capabilitiesLoading || companies.length === 0}
            >
              {prototypeCompanies.length > 0 && (
                <optgroup label="Prototype Pilot (4 Companies)">
                  {prototypeCompanies.map((c) => (
                    <option key={c.ticker} value={c.ticker}>
                      {c.ticker} — {c.company_name} ({c.sector})
                    </option>
                  ))}
                </optgroup>
              )}
              {expandedCompanies.length > 0 && (
                <optgroup label="Expanded Research Cohort (56 Companies)">
                  {expandedCompanies.map((c) => (
                    <option key={c.ticker} value={c.ticker}>
                      {c.ticker} — {c.company_name} ({c.sector})
                    </option>
                  ))}
                </optgroup>
              )}
            </select>

            {capabilitiesLoading && (
              <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                Loading cohort...
              </span>
            )}
            {capabilitiesError && (
              <span className="badge-tag badge-offline" title={capabilitiesError}>
                Universe Offline
              </span>
            )}
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
