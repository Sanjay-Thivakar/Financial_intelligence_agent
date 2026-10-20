import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import OverviewTab from './components/OverviewTab';
import MarketChartsTab from './components/MarketChartsTab';
import ModelLabTab from './components/ModelLabTab';
import PredictionResearchTab from './components/PredictionResearchTab';
import CompanyExplorerTab from './components/CompanyExplorerTab';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [companies, setCompanies] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState('AAPL');
  const [marketData, setMarketData] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [loadingMarket, setLoadingMarket] = useState(false);
  const [loadingEval, setLoadingEval] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);

  // 1. Initial Load: Companies list & Model Evaluation
  useEffect(() => {
    fetch('/api/companies')
      .then((res) => {
        if (!res.ok) throw new Error('API offline');
        return res.json();
      })
      .then((data) => {
        setCompanies(data);
        setApiConnected(true);
      })
      .catch((err) => {
        console.error('Failed to load eligible companies:', err);
        setApiConnected(false);
      });

    setLoadingEval(true);
    fetch('/api/models/evaluation')
      .then((res) => res.json())
      .then((data) => {
        setEvalData(data);
      })
      .catch((err) => console.error('Failed to load model evaluation:', err))
      .finally(() => setLoadingEval(false));
  }, []);

  // 2. Fetch Market Data whenever selectedTicker changes
  useEffect(() => {
    if (!selectedTicker) return;
    setLoadingMarket(true);
    fetch(`/api/companies/${selectedTicker}/market?limit=600`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load market for ${selectedTicker}`);
        return res.json();
      })
      .then((data) => {
        setMarketData(data);
      })
      .catch((err) => {
        console.error('Error fetching market series:', err);
        setMarketData(null);
      })
      .finally(() => setLoadingMarket(false));
  }, [selectedTicker]);

  const activeCompanyMeta = companies.find((c) => c.ticker === selectedTicker);

  return (
    <div className="terminal-layout">
      {/* Global Header & Company Subbar */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        companies={companies}
        selectedTicker={selectedTicker}
        setSelectedTicker={setSelectedTicker}
        apiConnected={apiConnected}
      />

      {/* Main Terminal Viewport */}
      <main className="terminal-content">
        {activeTab === 'overview' && (
          <OverviewTab
            companyMeta={activeCompanyMeta}
            marketData={marketData}
            loading={loadingMarket}
            onNavigateToCharts={() => setActiveTab('charts')}
          />
        )}

        {activeTab === 'charts' && (
          <MarketChartsTab
            marketData={marketData}
            selectedTicker={selectedTicker}
            loading={loadingMarket}
            companyMeta={activeCompanyMeta}
          />
        )}

        {activeTab === 'models' && (
          <ModelLabTab evalData={evalData} loading={loadingEval} />
        )}

        {activeTab === 'prediction' && (
          <PredictionResearchTab
            selectedTicker={selectedTicker}
            marketData={marketData}
            companies={companies}
            onSelectCompany={setSelectedTicker}
          />
        )}

        {activeTab === 'explorer' && (
          <CompanyExplorerTab
            companies={companies}
            selectedTicker={selectedTicker}
            onSelectCompany={setSelectedTicker}
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
