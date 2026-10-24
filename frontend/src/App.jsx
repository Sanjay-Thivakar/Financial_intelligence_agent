import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Header from './components/Header';
import OverviewTab from './components/OverviewTab';
import MarketChartsTab from './components/MarketChartsTab';
import ModelLabTab from './components/ModelLabTab';
import PredictionResearchTab from './components/PredictionResearchTab';
import CompanyExplorerTab from './components/CompanyExplorerTab';
import {
  parseNavigation,
  buildNavigationUrl,
  validateTicker,
  TAB_TO_URL,
  URL_TO_TAB,
  DEFAULT_TAB,
  DEFAULT_TICKER,
} from './navigation';

export default function App() {
  // 1. Authoritative Navigation & Active-Company State (Initialized from URL)
  const initialNav = useMemo(() => {
    if (typeof window !== 'undefined') {
      return parseNavigation(window.location.search);
    }
    return { ticker: DEFAULT_TICKER, tab: DEFAULT_TAB };
  }, []);

  const [activeTab, setActiveTab] = useState(initialNav.tab || DEFAULT_TAB);
  const [selectedTicker, setSelectedTicker] = useState(initialNav.ticker || DEFAULT_TICKER);

  // 2. Canonical Capability State
  const [capabilities, setCapabilities] = useState([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState(null);
  const [excludedEntities, setExcludedEntities] = useState([]);
  const [marketData, setMarketData] = useState(null);
  const [marketError, setMarketError] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [loadingMarket, setLoadingMarket] = useState(false);
  const [loadingEval, setLoadingEval] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);

  // Helper to synchronize URL query parameters with history support
  const syncUrl = useCallback((ticker, tab, mode = 'push') => {
    if (typeof window === 'undefined') return;
    const currentSearch = window.location.search;
    const currentParams = new URLSearchParams(currentSearch);
    const currentTicker = currentParams.get('ticker')?.toUpperCase();
    const currentTab = currentParams.get('tab')?.toLowerCase();
    const targetUrlTab = TAB_TO_URL[tab] || TAB_TO_URL[DEFAULT_TAB];

    // Avoid duplicate history entries if URL already matches
    if (currentTicker === ticker && currentTab === targetUrlTab) {
      return;
    }

    const newUrl = buildNavigationUrl(window.location.pathname, { ticker, tab }, currentSearch);
    if (mode === 'replace') {
      window.history.replaceState({ ticker, tab }, '', newUrl);
    } else {
      window.history.pushState({ ticker, tab }, '', newUrl);
    }
  }, []);

  // Deliberate user action: Switch active tab
  const handleTabChange = useCallback((newTab) => {
    const resolvedTab = URL_TO_TAB[newTab] || DEFAULT_TAB;
    if (resolvedTab === activeTab) return;
    setActiveTab(resolvedTab);
    syncUrl(selectedTicker, resolvedTab, 'push');
  }, [activeTab, selectedTicker, syncUrl]);

  // Deliberate user action: Select active company
  const handleSelectCompany = useCallback((newTicker) => {
    if (!newTicker) return;
    const validation = validateTicker(newTicker, capabilities);
    if (!validation.isValid) {
      console.warn(`Cannot select ticker ${newTicker}: ${validation.reason}`);
      return;
    }
    if (validation.canonicalTicker === selectedTicker) return;
    setSelectedTicker(validation.canonicalTicker);
    syncUrl(validation.canonicalTicker, activeTab, 'push');
  }, [capabilities, selectedTicker, activeTab, syncUrl]);

  // 3. Initial Load: Fetch Canonical Capability Inventory & Model Evaluation
  useEffect(() => {
    let isCurrent = true;
    setCapabilitiesLoading(true);
    fetch('/api/v1/companies/capabilities')
      .then((res) => {
        if (!res.ok) throw new Error(`Capabilities API error: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (isCurrent && data.companies) {
          setCapabilities(data.companies);
          setExcludedEntities(data.excluded_entities || []);
          setApiConnected(true);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          console.error('Failed to load capability inventory:', err);
          setCapabilitiesError(err.message);
          setApiConnected(false);
        }
      })
      .finally(() => {
        if (isCurrent) setCapabilitiesLoading(false);
      });

    setLoadingEval(true);
    fetch('/api/models/evaluation')
      .then((res) => res.json())
      .then((data) => {
        if (isCurrent) setEvalData(data);
      })
      .catch((err) => console.error('Failed to load model evaluation:', err))
      .finally(() => {
        if (isCurrent) setLoadingEval(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  // 4. URL Normalization & Validation once Capability Inventory is loaded
  useEffect(() => {
    if (!capabilitiesLoading && capabilities.length > 0) {
      const validation = validateTicker(selectedTicker, capabilities);
      if (!validation.isValid) {
        console.warn(`Selected ticker ${selectedTicker} is invalid or excluded; recovering to ${DEFAULT_TICKER}`);
        setSelectedTicker(DEFAULT_TICKER);
        syncUrl(DEFAULT_TICKER, activeTab, 'replace');
      } else {
        // Normalize current URL query parameters without creating extra history entry
        syncUrl(validation.canonicalTicker, activeTab, 'replace');
      }
    }
  }, [capabilitiesLoading, capabilities, selectedTicker, activeTab, syncUrl]);

  // 5. Browser History PopState (Back / Forward Navigation)
  useEffect(() => {
    const handlePopState = () => {
      const nav = parseNavigation(window.location.search);
      setActiveTab(nav.tab);

      if (nav.ticker) {
        if (capabilities.length > 0) {
          const validation = validateTicker(nav.ticker, capabilities);
          if (validation.isValid) {
            setSelectedTicker(validation.canonicalTicker);
          } else {
            console.warn(`Popstate yielded invalid ticker ${nav.ticker}; normalizing to ${DEFAULT_TICKER}`);
            setSelectedTicker(DEFAULT_TICKER);
            syncUrl(DEFAULT_TICKER, nav.tab, 'replace');
          }
        } else {
          setSelectedTicker(nav.ticker);
        }
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [capabilities, syncUrl]);

  // 6. Derive normalized companies array for child components
  const companies = useMemo(() => {
    return capabilities.map((c) => ({
      ticker: c.identity.canonical_ticker,
      company_name: c.identity.company_name,
      company_id: c.identity.company_id,
      cik: c.identity.cik,
      sector: c.identity.sector,
      total_sessions: c.market_artifact.total_sessions,
      min_date: c.market_artifact.earliest_date,
      max_date: c.market_artifact.latest_date,
      is_prototype: ['AAPL', 'JPM', 'GOOG', 'TSLA'].includes(c.identity.canonical_ticker),
      capability: c,
    }));
  }, [capabilities]);

  // 7. Fetch Market Data whenever selectedTicker changes with race condition protection
  useEffect(() => {
    if (!selectedTicker) return;
    let isCurrent = true;
    setLoadingMarket(true);
    setMarketError(null);

    fetch(`/api/companies/${selectedTicker}/market?limit=600`)
      .then((res) => {
        if (!res.ok) throw new Error(`Market data for ${selectedTicker} unavailable (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (isCurrent) {
          setMarketData(data);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          console.error(`Error fetching market series for ${selectedTicker}:`, err);
          setMarketData(null);
          setMarketError(err.message);
        }
      })
      .finally(() => {
        if (isCurrent) {
          setLoadingMarket(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [selectedTicker]);

  // 8. Active company metadata derived from capability inventory
  const activeCapability = capabilities.find((c) => c.identity.canonical_ticker === selectedTicker);
  const activeCompanyMeta = useMemo(() => {
    if (!activeCapability) return null;
    const id = activeCapability.identity;
    const mkt = activeCapability.market_artifact;
    const mm = activeCapability.multi_modal;
    return {
      ticker: id.canonical_ticker,
      company_id: id.company_id,
      company_name: id.company_name,
      cik: id.cik,
      sector: id.sector,
      membership_interval:
        id.universe_membership === 'HISTORICAL_RESEARCH_COHORT'
          ? 'Historical Research Cohort (1970–2023)'
          : '1980–Present',
      min_date: mkt.earliest_date || 'N/A',
      max_date: mkt.latest_date || 'N/A',
      total_sessions: mkt.total_sessions || 0,
      sec_coverage_status:
        mm.sec_fundamentals_status === 'SUPPORTED' ? 'active_with_facts' : 'not_downloaded',
      news_coverage_status:
        mm.news_status === 'SUPPORTED' ? 'active_with_headlines' : 'excluded_by_policy',
      capability: activeCapability,
    };
  }, [activeCapability]);

  return (
    <div className="terminal-layout">
      {/* Global Header & Company Subbar */}
      <Header
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        companies={companies}
        selectedTicker={selectedTicker}
        setSelectedTicker={handleSelectCompany}
        apiConnected={apiConnected}
        capabilitiesLoading={capabilitiesLoading}
        capabilitiesError={capabilitiesError}
        excludedEntities={excludedEntities}
        activeCompanyMeta={activeCompanyMeta}
      />

      {/* Main Terminal Viewport */}
      <main className="terminal-content">
        {activeTab === 'overview' && (
          <OverviewTab
            companyMeta={activeCompanyMeta}
            marketData={marketData}
            marketLoading={loadingMarket}
            capabilitiesLoading={capabilitiesLoading}
            marketError={marketError}
            capabilitiesError={capabilitiesError}
            selectedTicker={selectedTicker}
            onNavigateToCharts={() => handleTabChange('charts')}
          />
        )}

        {activeTab === 'charts' && (
          <MarketChartsTab
            marketData={marketData}
            selectedTicker={selectedTicker}
            loading={loadingMarket}
            marketError={marketError}
            companyMeta={activeCompanyMeta}
          />
        )}

        {activeTab === 'models' && (
          <ModelLabTab
            evalData={evalData}
            loading={loadingEval}
            selectedTicker={selectedTicker}
            companyMeta={activeCompanyMeta}
          />
        )}

        {activeTab === 'prediction' && (
          <PredictionResearchTab
            selectedTicker={selectedTicker}
            companyMeta={activeCompanyMeta}
            marketData={marketData}
            companies={companies}
            onSelectCompany={handleSelectCompany}
          />
        )}

        {activeTab === 'explorer' && (
          <CompanyExplorerTab
            companies={companies}
            selectedTicker={selectedTicker}
            onSelectCompany={handleSelectCompany}
            onNavigateTab={handleTabChange}
          />
        )}
      </main>

      {/* Terminal Footer */}
      <footer className="terminal-footer">
        <div>
          <span>FINANCIAL INTELLIGENCE AGENT — PROTOTYPE TERMINAL</span>
          <span style={{ margin: '0 8px', opacity: 0.3 }}>|</span>
          <span>RESEARCH USE ONLY — NOT INVESTMENT ADVICE</span>
        </div>
        <div className="font-mono">
          <span>Purge: 5 Trading Days</span>
          <span style={{ margin: '0 8px', opacity: 0.3 }}>|</span>
          <span>Target: 5-Session Forward Total Return</span>
          <span style={{ margin: '0 8px', opacity: 0.3 }}>|</span>
          <span>Mode: Offline Verified Parquet</span>
        </div>
      </footer>
    </div>
  );
}
