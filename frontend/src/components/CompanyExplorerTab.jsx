import React, { useState, useEffect, useMemo } from 'react';
import {
  Database,
  Search,
  Filter,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowRight,
  Clock,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  SlidersHorizontal,
  Layers,
  Activity,
  Info,
  X,
  TrendingUp,
  TrendingDown,
  Lock,
  BarChart2,
  Eye,
} from 'lucide-react';

const MODEL_OPTIONS = [
  { id: 'ridge_regression', label: 'Ridge Regression (Phase 5J Benchmark — Default)', tag: 'Validated' },
  { id: 'hist_gradient_boosting', label: 'HistGradientBoosting (Nonlinear Tree GBRT)', tag: 'Experimental' },
  { id: 'elastic_net', label: 'ElasticNet (L1/L2 Regularized)', tag: 'Linear ML' },
  { id: 'ridge_cs_demeaned', label: 'Ridge CS Demeaned (Market Drift Removed)', tag: 'CS Transform' },
  { id: 'ridge_sector_neutral', label: 'Ridge Sector-Neutral (Residualized)', tag: 'Sector Transform' },
  { id: 'zero_baseline', label: 'Reference 0: Naive Zero Return', tag: 'Baseline' },
  { id: 'median_baseline', label: 'Reference 1: Historical Median', tag: 'Baseline' },
];

const FOLD_DATES = [
  { id: 'latest', label: 'Latest Available (Per-Company Observation)' },
  { id: '2020-06-03', label: 'Fold 3 Holdout (2020-06-03) — 5 Truncated Unavailable' },
  { id: '2020-03-25', label: 'Fold 2 COVID Crash (2020-03-25) — 60 Active' },
  { id: '2020-01-24', label: 'Fold 1 Normal Panel (2020-01-24) — 60 Active' },
  { id: '2019-11-18', label: 'Fold 0 Earliest OOS (2019-11-18) — 60 Active' },
];

export default function CompanyExplorerTab({ companies, selectedTicker, onSelectCompany }) {
  // Screener state
  const [screenerData, setScreenerData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedModel, setSelectedModel] = useState('ridge_regression');
  const [selectedFoldDate, setSelectedFoldDate] = useState('latest');

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSector, setSelectedSector] = useState('all');
  const [selectedSignal, setSelectedSignal] = useState('all');
  const [selectedCoverage, setSelectedCoverage] = useState('all');
  const [selectedRiskStatus, setSelectedRiskStatus] = useState('all');

  // Sorting & Pagination
  const [sortField, setSortField] = useState('ticker');
  const [sortDirection, setSortDirection] = useState('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);

  // Company Detail Inspection View
  const [inspectingTicker, setInspectingTicker] = useState(null);
  const [detailDate, setDetailDate] = useState(null);
  const [companyDetail, setCompanyDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [chartMode, setChartMode] = useState('candlestick'); // 'candlestick' or 'line'
  const [hoveredPoint, setHoveredPoint] = useState(null);

  // 1. Fetch 60-Company Screener Data
  const fetchScreener = () => {
    setLoading(true);
    setError(null);
    const dateParam = selectedFoldDate !== 'latest' ? `&as_of_date=${selectedFoldDate}` : '';
    fetch(`/api/research/companies?model_id=${selectedModel}${dateParam}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load research screener.`);
        return res.json();
      })
      .then((data) => {
        setScreenerData(data);
      })
      .catch((err) => {
        console.error('Error fetching screener:', err);
        setError(err.message || 'Failed to connect to research API.');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchScreener();
  }, [selectedModel, selectedFoldDate]);

  // 2. Fetch Company Detail Data when inspectingTicker or detailDate changes
  useEffect(() => {
    if (!inspectingTicker) {
      setCompanyDetail(null);
      return;
    }

    setLoadingDetail(true);
    setDetailError(null);
    const dateParam = detailDate ? `&as_of_date=${detailDate}` : '';
    fetch(`/api/research/companies/${inspectingTicker}?model_id=${selectedModel}${dateParam}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load company details for ${inspectingTicker}.`);
        return res.json();
      })
      .then((data) => {
        setCompanyDetail(data);
      })
      .catch((err) => {
        console.error('Error fetching company detail:', err);
        setDetailError(err.message || `Failed to fetch data for ${inspectingTicker}`);
      })
      .finally(() => setLoadingDetail(false));
  }, [inspectingTicker, selectedModel, detailDate]);

  // Filtered and Sorted Company List
  const processedCompanies = useMemo(() => {
    if (!screenerData || !screenerData.companies) return [];

    let list = [...screenerData.companies];

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (c) => c.ticker.toLowerCase().includes(q) || c.company_name.toLowerCase().includes(q)
      );
    }

    // Sector filter
    if (selectedSector !== 'all') {
      list = list.filter((c) => c.sector.toLowerCase() === selectedSector.toLowerCase());
    }

    // Signal filter
    if (selectedSignal !== 'all') {
      list = list.filter((c) => c.signal.toLowerCase() === selectedSignal.toLowerCase());
    }

    // Coverage filter
    if (selectedCoverage === 'complete') {
      list = list.filter((c) => !c.is_truncated);
    } else if (selectedCoverage === 'truncated') {
      list = list.filter((c) => c.is_truncated);
    }

    // Risk Status filter
    if (selectedRiskStatus === 'passed') {
      list = list.filter((c) => c.risk_status.includes('Passed'));
    } else if (selectedRiskStatus === 'volatility') {
      list = list.filter((c) => c.risk_status.includes('Volatility'));
    } else if (selectedRiskStatus === 'cost') {
      list = list.filter((c) => c.risk_status.includes('Return Hurdle') || c.risk_status.includes('Cost'));
    } else if (selectedRiskStatus === 'buffer') {
      list = list.filter((c) => c.risk_status.includes('Buffer'));
    }

    // Sorting
    list.sort((a, b) => {
      let valA = a[sortField];
      let valB = b[sortField];

      if (valA === null || valA === undefined) valA = -999999;
      if (valB === null || valB === undefined) valB = -999999;

      if (typeof valA === 'string') {
        const comp = valA.localeCompare(valB);
        return sortDirection === 'asc' ? comp : -comp;
      }

      return sortDirection === 'asc' ? valA - valB : valB - valA;
    });

    return list;
  }, [
    screenerData,
    searchQuery,
    selectedSector,
    selectedSignal,
    selectedCoverage,
    selectedRiskStatus,
    sortField,
    sortDirection,
  ]);

  // Pagination calculation
  const totalItems = processedCompanies.length;
  const totalPages = Math.ceil(totalItems / pageSize) || 1;
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const pageItems = processedCompanies.slice(startIndex, startIndex + pageSize);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setCurrentPage(1);
  };

  const resetFilters = () => {
    setSearchQuery('');
    setSelectedSector('all');
    setSelectedSignal('all');
    setSelectedCoverage('all');
    setSelectedRiskStatus('all');
    setSelectedFoldDate('latest');
    setSortField('ticker');
    setSortDirection('asc');
    setCurrentPage(1);
  };

  const handleInspectCompany = (ticker, customDate = null) => {
    setInspectingTicker(ticker);
    setDetailDate(customDate || (selectedFoldDate !== 'latest' ? selectedFoldDate : null));
    if (onSelectCompany) {
      onSelectCompany(ticker);
    }
  };

  const handleCloseDetail = () => {
    setInspectingTicker(null);
    setDetailDate(null);
    setCompanyDetail(null);
    setHoveredPoint(null);
  };

  // Keyboard shortcut for Esc to close detail view
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && inspectingTicker) {
        handleCloseDetail();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [inspectingTicker]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Historical Research Disclaimers & Mode Banner */}
      <div
        className="card"
        style={{
          borderLeft: '4px solid var(--accent-amber)',
          background: 'rgba(245, 158, 11, 0.04)',
          padding: '14px 18px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertTriangle size={18} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                Historical Research Mode — 60-Company Cohort (Archived 2019–2020 Panels)
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px', lineHeight: 1.5 }}>
                Predictions and experimental signals are based strictly on archived out-of-sample walk-forward panels (September 2019 to June 2020), <strong>not current market conditions</strong>. No real orders are executed and no signals constitute personalized investment advice.
              </div>
            </div>
          </div>
          <span className="badge-tag badge-experimental font-mono">Archive Sandbox Mode</span>
        </div>
      </div>

      {/* Model Selection & KPI Overview Grid */}
      <div className="card" style={{ padding: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SlidersHorizontal size={14} style={{ color: 'var(--accent-cyan)' }} />
            <span style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-primary)' }}>
              Forecast Model & Inference Engine
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Evaluated Model:</label>
            <select
              value={selectedModel}
              onChange={(e) => {
                setSelectedModel(e.target.value);
                setCurrentPage(1);
              }}
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-medium)',
                color: 'var(--text-primary)',
                padding: '5px 10px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                fontFamily: 'var(--font-sans)',
                cursor: 'pointer',
              }}
              id="select-screener-model"
            >
              {MODEL_OPTIONS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="chart-toggle-btn"
              onClick={fetchScreener}
              title="Refresh screener data"
              disabled={loading}
              style={{ padding: '5px 8px' }}
              id="btn-refresh-screener"
            >
              <RefreshCw size={12} className={loading ? 'spin' : ''} />
            </button>
          </div>
        </div>

        {/* Screener KPI Ribbon */}
        {screenerData && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px' }}>
            <div style={{ background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Validated Universe</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '2px' }}>
                {screenerData.total_cohort_count} <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 400 }}>Companies</span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>11 GICS Sectors</div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Displayed Cohort</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent-cyan)', marginTop: '2px' }}>
                {processedCompanies.length} <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 400 }}>/ 60</span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                {processedCompanies.length === 60 ? 'Full Panel Active' : 'Filter Applied'}
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>BUY Signals</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent-green)', marginTop: '2px' }}>
                {screenerData.signal_summary?.BUY || 0}
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                Net Return &ge; +1.50% & All Gates Passed
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>HOLD Signals</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-secondary)', marginTop: '2px' }}>
                {screenerData.signal_summary?.HOLD || 0}
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                Risk-Gated or Return in Neutral Buffer
              </div>
            </div>

            <div style={{ background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Data Coverage</div>
              <div className="font-mono" style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)', marginTop: '2px' }}>
                55 <span style={{ fontSize: '11px', color: 'var(--accent-amber)', fontWeight: 400 }}>+ 5 Trunc</span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                BLK, CSCO, CVS, EQIX, FCX (315 ses)
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Detail Inspection Modal / View */}
      {inspectingTicker && (
        <div
          className="card"
          style={{
            border: '2px solid var(--accent-blue)',
            boxShadow: 'var(--shadow-terminal)',
            background: 'var(--bg-surface)',
            padding: '20px',
          }}
          id="company-detail-modal"
        >
          {/* Detail Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-medium)', paddingBottom: '14px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button
                type="button"
                className="chart-toggle-btn active"
                onClick={handleCloseDetail}
                style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', fontSize: '11px' }}
                id="btn-back-to-screener"
              >
                <ChevronLeft size={14} />
                <span>Back to 60-Company Screener</span>
              </button>
              <div>
                <span className="font-mono" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent-blue)' }}>
                  {inspectingTicker}
                </span>
                <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginLeft: '10px' }}>
                  {companyDetail?.company_name || 'Loading company profile...'}
                </span>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '8px' }}>
                  ({companyDetail?.sector || ''})
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {companyDetail?.is_truncated && (
                <span className="badge-tag badge-offline" title={companyDetail?.limitations_note || ''}>
                  <AlertTriangle size={12} />
                  <span>Truncated 86.8% Coverage</span>
                </span>
              )}
              {companyDetail?.signal && (
                <span
                  className="badge-tag"
                  style={{
                    fontSize: '12px',
                    fontWeight: 700,
                    padding: '4px 10px',
                    background: companyDetail.signal === 'BUY' ? 'rgba(16, 185, 129, 0.15)' : companyDetail.signal === 'SELL' ? 'rgba(244, 63, 94, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                    color: companyDetail.signal === 'BUY' ? 'var(--accent-green)' : companyDetail.signal === 'SELL' ? 'var(--accent-red)' : 'var(--text-secondary)',
                    border: `1px solid ${companyDetail.signal === 'BUY' ? 'var(--accent-green)' : companyDetail.signal === 'SELL' ? 'var(--accent-red)' : 'var(--border-medium)'}`,
                  }}
                >
                  Signal: {companyDetail.signal}
                </span>
              )}
              <button
                type="button"
                onClick={handleCloseDetail}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: '4px',
                }}
                title="Close detail view (Esc)"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          {loadingDetail && (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <div className="font-mono">Loading company research profile and 8-stage decision funnel...</div>
            </div>
          )}

          {detailError && (
            <div style={{ padding: '20px', background: 'rgba(244, 63, 94, 0.1)', color: 'var(--accent-red)', borderRadius: 'var(--radius-sm)' }}>
              <strong>Error Loading Company Details:</strong> {detailError}
            </div>
          )}

          {companyDetail && !loadingDetail && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Quick Metrics Bar */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' }}>
                <div style={{ background: 'var(--bg-card)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Observation Date</span>
                    {companyDetail.available_prediction_dates?.length > 1 && (
                      <span style={{ fontSize: '9px', color: 'var(--accent-blue)' }}>
                        {companyDetail.available_prediction_dates.length} OOS Dates
                      </span>
                    )}
                  </div>
                  {companyDetail.available_prediction_dates?.length > 1 ? (
                    <select
                      value={companyDetail.observation_date || ''}
                      onChange={(e) => setDetailDate(e.target.value)}
                      style={{
                        background: 'transparent',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '13px',
                        fontWeight: 600,
                        marginTop: '4px',
                        width: '100%',
                        padding: '2px 4px',
                        borderRadius: '3px',
                        cursor: 'pointer',
                      }}
                      id="select-detail-date"
                      title="Inspect model prediction and funnel for a specific historical OOS date"
                    >
                      {companyDetail.available_prediction_dates.slice().reverse().map((d) => (
                        <option key={d} value={d} style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)' }}>
                          {d} {d === companyDetail.available_prediction_dates[companyDetail.available_prediction_dates.length - 1] ? '(Latest)' : ''}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="font-mono" style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                      {companyDetail.observation_date || 'N/A'}
                    </div>
                  )}
                  <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '4px' }}>
                    {companyDetail.observation_date ? `Fold ${companyDetail.fold ?? 'OOS'} Observation` : 'Date Outside Coverage'}
                  </div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Gross 5-Day Forecast</div>
                  <div className="font-mono" style={{ fontSize: '15px', fontWeight: 700, color: (companyDetail.predicted_return || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', marginTop: '2px' }}>
                    {companyDetail.predicted_return_pct || 'Unavailable'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>T+1 Open &rarr; T+5 Close</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Net Expected Return</div>
                  <div className="font-mono" style={{ fontSize: '15px', fontWeight: 700, color: (companyDetail.expected_net_return || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', marginTop: '2px' }}>
                    {companyDetail.expected_net_return_pct || 'Unavailable'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>After 15 bps round-trip friction</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Residual Uncertainty</div>
                  <div className="font-mono" style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                    {companyDetail.forecast_uncertainty_pct || 'Unavailable'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>Ceiling: 8.00% &sigma;</div>
                </div>

                <div style={{ background: 'var(--bg-card)', padding: '10px 12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model Provenance</div>
                  <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--accent-cyan)', marginTop: '4px' }}>
                    {companyDetail.model_id || 'N/A'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                    17 Market Technical Features
                  </div>
                </div>
              </div>

              {/* Truncation / Data Limitations Warning Alert */}
              {companyDetail.limitations_note && (
                <div style={{ background: 'rgba(234, 179, 8, 0.08)', borderLeft: '3px solid var(--accent-amber)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  <strong style={{ color: 'var(--accent-amber)' }}>Data Coverage Limitation:</strong> {companyDetail.limitations_note}
                </div>
              )}

              {/* Historical Price Chart Section */}
              <div style={{ background: 'var(--bg-card)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <BarChart2 size={14} style={{ color: 'var(--accent-blue)' }} />
                    <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)' }}>
                      Archived Historical Daily Prices (2018–2020)
                    </span>
                    <span className="badge-tag badge-status">Tiingo Split-Adjusted</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <button
                      type="button"
                      className={`chart-toggle-btn ${chartMode === 'candlestick' ? 'active' : ''}`}
                      onClick={() => setChartMode('candlestick')}
                      style={{ fontSize: '10px', padding: '3px 8px' }}
                    >
                      Candlestick
                    </button>
                    <button
                      type="button"
                      className={`chart-toggle-btn ${chartMode === 'line' ? 'active' : ''}`}
                      onClick={() => setChartMode('line')}
                      style={{ fontSize: '10px', padding: '3px 8px' }}
                    >
                      Adjusted Close Line
                    </button>
                  </div>
                </div>

                {/* SVG Native Price Chart */}
                {companyDetail.historical_price_series && companyDetail.historical_price_series.length > 0 ? (
                  <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
                    {hoveredPoint && (
                      <div
                        style={{
                          position: 'absolute',
                          top: '10px',
                          right: '15px',
                          background: 'var(--bg-elevated)',
                          border: '1px solid var(--border-medium)',
                          padding: '6px 10px',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          zIndex: 10,
                          pointerEvents: 'none',
                        }}
                      >
                        <div>Date: <strong>{hoveredPoint.trading_date}</strong></div>
                        <div>Close: <strong>${hoveredPoint.close.toFixed(2)}</strong> | Adj: <strong>${hoveredPoint.adjusted_close.toFixed(2)}</strong></div>
                        <div>O: ${hoveredPoint.open.toFixed(2)} | H: ${hoveredPoint.high.toFixed(2)} | L: ${hoveredPoint.low.toFixed(2)}</div>
                        <div>Vol: {(hoveredPoint.volume / 1e6).toFixed(1)}M shares</div>
                      </div>
                    )}

                    <svg
                      viewBox="0 0 800 240"
                      style={{ width: '100%', height: '240px', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)' }}
                      onMouseLeave={() => setHoveredPoint(null)}
                    >
                      {/* Price Scale Computation */}
                      {(() => {
                        const series = companyDetail.historical_price_series;
                        const prices = series.map((s) => s.close);
                        const minP = Math.min(...prices) * 0.95;
                        const maxP = Math.max(...prices) * 1.05;
                        const pRange = maxP - minP || 1;

                        const chartW = 760;
                        const chartH = 170;
                        const padL = 30;
                        const padT = 15;
                        const volH = 40;
                        const maxVol = Math.max(...series.map((s) => s.volume)) || 1;

                        const stepX = chartW / series.length;

                        // Grid lines
                        const gridTicks = [0.25, 0.5, 0.75, 1.0];

                        return (
                          <g>
                            {/* Horizontal Grid */}
                            {gridTicks.map((tick, idx) => {
                              const y = padT + chartH * (1 - tick);
                              const priceLabel = minP + pRange * tick;
                              return (
                                <g key={idx}>
                                  <line x1={padL} y1={y} x2={padL + chartW} y2={y} stroke="var(--border-subtle)" strokeDasharray="3 3" />
                                  <text x={padL + chartW - 5} y={y - 3} fill="var(--text-dim)" fontSize="9" textAnchor="end" fontFamily="var(--font-mono)">
                                    ${priceLabel.toFixed(1)}
                                  </text>
                                </g>
                              );
                            })}

                            {/* Chart Rendering */}
                            {chartMode === 'candlestick' ? (
                              series.map((pt, i) => {
                                const x = padL + i * stepX + stepX / 2;
                                const yOpen = padT + chartH * (1 - (pt.open - minP) / pRange);
                                const yClose = padT + chartH * (1 - (pt.close - minP) / pRange);
                                const yHigh = padT + chartH * (1 - (pt.high - minP) / pRange);
                                const yLow = padT + chartH * (1 - (pt.low - minP) / pRange);
                                const isUp = pt.close >= pt.open;
                                const color = isUp ? 'var(--accent-green)' : 'var(--accent-red)';

                                const barTop = Math.min(yOpen, yClose);
                                const barH = Math.max(Math.abs(yClose - yOpen), 1);
                                const barW = Math.max(stepX * 0.6, 2);

                                // Volume bar
                                const volBarH = (pt.volume / maxVol) * volH;
                                const volY = padT + chartH + 10 + (volH - volBarH);

                                return (
                                  <g
                                    key={i}
                                    onMouseEnter={() => setHoveredPoint(pt)}
                                    style={{ cursor: 'crosshair' }}
                                  >
                                    {/* Wick */}
                                    <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1" />
                                    {/* Candle body */}
                                    <rect
                                      x={x - barW / 2}
                                      y={barTop}
                                      width={barW}
                                      height={barH}
                                      fill={color}
                                    />
                                    {/* Volume bar */}
                                    <rect
                                      x={x - barW / 2}
                                      y={volY}
                                      width={barW}
                                      height={volBarH}
                                      fill={color}
                                      opacity="0.3"
                                    />
                                  </g>
                                );
                              })
                            ) : (
                              // Line mode
                              <g>
                                <path
                                  d={series.reduce((acc, pt, i) => {
                                    const x = padL + i * stepX + stepX / 2;
                                    const y = padT + chartH * (1 - (pt.adjusted_close - minP) / pRange);
                                    return i === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
                                  }, '')}
                                  fill="none"
                                  stroke="var(--accent-blue)"
                                  strokeWidth="1.5"
                                />
                                {series.map((pt, i) => {
                                  const x = padL + i * stepX + stepX / 2;
                                  const volBarH = (pt.volume / maxVol) * volH;
                                  const volY = padT + chartH + 10 + (volH - volBarH);
                                  return (
                                    <rect
                                      key={i}
                                      x={x - Math.max(stepX * 0.4, 1)}
                                      y={volY}
                                      width={Math.max(stepX * 0.8, 2)}
                                      height={volBarH}
                                      fill="var(--accent-blue)"
                                      opacity="0.25"
                                      onMouseEnter={() => setHoveredPoint(pt)}
                                      style={{ cursor: 'crosshair' }}
                                    />
                                  );
                                })}
                              </g>
                            )}

                            {/* Date ticks on bottom */}
                            {[0, Math.floor(series.length * 0.25), Math.floor(series.length * 0.5), Math.floor(series.length * 0.75), series.length - 1].map((idx) => {
                              const s = series[idx];
                              if (!s) return null;
                              const x = padL + idx * stepX;
                              return (
                                <text
                                  key={idx}
                                  x={x}
                                  y={padT + chartH + volH + 20}
                                  fill="var(--text-dim)"
                                  fontSize="9"
                                  fontFamily="var(--font-mono)"
                                  textAnchor="middle"
                                >
                                  {s.trading_date}
                                </text>
                              );
                            })}
                          </g>
                        );
                      })()}
                    </svg>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', marginTop: '6px' }}>
                      <span>Showing {companyDetail.historical_price_series.length} historical trading sessions (T-250 to Observation Date)</span>
                      <span>Volume (Bottom Bars) | Split & Dividend Adjusted</span>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No market price series available in local dataset for this asset.
                  </div>
                )}
              </div>

              {/* Complete 8-Stage Decision Funnel Card */}
              <div style={{ background: 'var(--bg-card)', padding: '16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers size={14} style={{ color: 'var(--accent-purple)' }} />
                    <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)' }}>
                      Transparent 8-Stage Decision Funnel & Risk Gate Diagnostics
                    </span>
                  </div>
                  <span className="badge-tag badge-status">Policy Invariants Enforced</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {companyDetail.funnel_stages && companyDetail.funnel_stages.map((stage) => {
                    const isPass = stage.status === 'PASS';
                    const isFail = stage.status === 'FAIL';
                    const isHold = stage.status === 'HOLD';
                    const isNotEval = stage.status === 'NOT EVALUATED';

                    const badgeColor = isPass
                      ? 'var(--accent-green)'
                      : isFail
                      ? 'var(--accent-red)'
                      : isHold
                      ? 'var(--accent-amber)'
                      : 'var(--text-dim)';
                    const badgeBg = isPass
                      ? 'rgba(16, 185, 129, 0.12)'
                      : isFail
                      ? 'rgba(244, 63, 94, 0.12)'
                      : isHold
                      ? 'rgba(245, 158, 11, 0.12)'
                      : 'rgba(100, 116, 139, 0.12)';

                    return (
                      <div
                        key={stage.stage_number}
                        style={{
                          background: 'var(--bg-surface)',
                          border: `1px solid ${isFail ? 'rgba(244, 63, 94, 0.4)' : isPass ? 'var(--border-subtle)' : 'var(--border-subtle)'}`,
                          borderLeft: `4px solid ${badgeColor}`,
                          borderRadius: 'var(--radius-sm)',
                          padding: '10px 14px',
                          display: 'flex',
                          alignItems: 'flex-start',
                          justifyContent: 'space-between',
                          gap: '12px',
                        }}
                      >
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
                            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              Stage {stage.stage_number}
                            </span>
                            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {stage.stage_name}
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            {stage.explanation}
                          </div>
                          {stage.threshold_applied && (
                            <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '3px' }}>
                              <strong>Threshold Rule:</strong> {stage.threshold_applied}
                            </div>
                          )}
                        </div>

                        <div style={{ textAlign: 'right', flexShrink: 0 }}>
                          <span
                            className="font-mono"
                            style={{
                              display: 'inline-block',
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 8px',
                              borderRadius: '3px',
                              background: badgeBg,
                              color: badgeColor,
                              border: `1px solid ${badgeColor}`,
                            }}
                          >
                            {stage.status}
                          </span>
                          {stage.metric_value && (
                            <div className="font-mono" style={{ fontSize: '11px', color: 'var(--text-primary)', marginTop: '4px', fontWeight: 600 }}>
                              {stage.metric_value}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Transaction Cost Breakdown Footer */}
                <div style={{ marginTop: '14px', background: 'var(--bg-surface)', padding: '10px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-dim)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                    Institutional Transaction Cost Model (15.0 bps Round-Trip Invariant):
                  </div>
                  <div>
                    &bull; Entry Fee: <strong>2.5 bps</strong> | Exit Fee: <strong>2.5 bps</strong> | Half-Spread: <strong>2.5 bps</strong> | Slippage: <strong>2.5 bps</strong>
                    <br />
                    &bull; Directional Threshold Policy: Net BUY require &ge; +1.50% net return (gross &ge; +1.65%). Net SELL require &le; -1.50% net return.
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main 60-Company Stock Screener Table Card */}
      <div className="card" style={{ padding: '16px' }}>
        {/* Controls Toolbar: Search & Filters */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Database size={15} style={{ color: 'var(--accent-blue)' }} />
              <span className="card-title" style={{ fontSize: '14px' }}>
                60-Company Out-of-Sample Research Universe
              </span>
              <span className="badge-tag badge-status">
                {processedCompanies.length} / 60 Filtered
              </span>
            </div>

            <button
              type="button"
              className="chart-toggle-btn"
              onClick={resetFilters}
              style={{ fontSize: '11px', padding: '4px 10px' }}
              id="btn-reset-filters"
            >
              Reset Filters
            </button>
          </div>

          {/* Filter Controls Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
            {/* Search Input */}
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: '10px', top: '9px', color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search ticker or name..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px 6px 28px',
                  color: 'var(--text-primary)',
                  fontSize: '11px',
                }}
                id="input-screener-search"
              />
            </div>

            {/* Sector Filter */}
            <div>
              <select
                value={selectedSector}
                onChange={(e) => {
                  setSelectedSector(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                  color: 'var(--text-primary)',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
                id="select-sector-filter"
              >
                <option value="all">All Sectors (11 Sectors)</option>
                {screenerData?.available_sectors?.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            {/* Signal Filter */}
            <div>
              <select
                value={selectedSignal}
                onChange={(e) => {
                  setSelectedSignal(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                  color: 'var(--text-primary)',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
                id="select-signal-filter"
              >
                <option value="all">All Signals (BUY, HOLD, SELL, UNAVAIL)</option>
                <option value="buy">BUY Only</option>
                <option value="hold">HOLD Only</option>
                <option value="sell">SELL Only</option>
                <option value="unavailable">UNAVAILABLE Only</option>
              </select>
            </div>

            {/* Coverage / Truncation Filter */}
            <div>
              <select
                value={selectedCoverage}
                onChange={(e) => {
                  setSelectedCoverage(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                  color: 'var(--text-primary)',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
                id="select-coverage-filter"
              >
                <option value="all">All Coverage (Complete & Truncated)</option>
                <option value="complete">Complete Only (363 Sessions)</option>
                <option value="truncated">Truncated Only (BLK, CSCO, CVS, EQIX, FCX)</option>
              </select>
            </div>

            {/* Risk Status Filter */}
            <div>
              <select
                value={selectedRiskStatus}
                onChange={(e) => {
                  setSelectedRiskStatus(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                  color: 'var(--text-primary)',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
                id="select-risk-filter"
              >
                <option value="all">All Risk Gate Statuses</option>
                <option value="passed">All Risk Gates Passed</option>
                <option value="volatility">Blocked by Volatility Gate (&gt; 15%)</option>
                <option value="cost">Blocked by Return Hurdle (&lt; 0.65%)</option>
                <option value="buffer">Hold in Return Buffer (-1.5% to +1.5%)</option>
              </select>
            </div>

            {/* Historical Fold / Date Snapshot Filter */}
            <div>
              <select
                value={selectedFoldDate}
                onChange={(e) => {
                  setSelectedFoldDate(e.target.value);
                  setCurrentPage(1);
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '6px 10px',
                  color: 'var(--accent-blue)',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                id="select-fold-date-filter"
                title="Select historical walk-forward fold snapshot or latest available observation"
              >
                {FOLD_DATES.map((f) => (
                  <option key={f.id} value={f.id}>{f.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <div className="font-mono">Loading 60-company research screener from offline Parquet archive...</div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div style={{ padding: '20px', background: 'rgba(244, 63, 94, 0.1)', color: 'var(--accent-red)', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
            <div><strong>API Connection Error:</strong> {error}</div>
            <button
              type="button"
              className="chart-toggle-btn active"
              onClick={fetchScreener}
              style={{ marginTop: '10px', padding: '6px 16px' }}
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Screener Data Table */}
        {!loading && !error && (
          <>
            {pageItems.length === 0 ? (
              <div style={{ padding: '50px', textAlign: 'center', color: 'var(--text-muted)', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)' }}>
                <AlertTriangle size={24} style={{ color: 'var(--accent-amber)', marginBottom: '8px' }} />
                <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  No companies match your search and filter criteria.
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Try resetting the sector or signal filters to discover all 60 cohort assets.
                </div>
                <button
                  type="button"
                  className="chart-toggle-btn active"
                  onClick={resetFilters}
                  style={{ marginTop: '12px', padding: '6px 14px' }}
                >
                  Clear All Filters
                </button>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-medium)', color: 'var(--text-muted)' }}>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('ticker')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>Ticker & Company</span>
                          {sortField === 'ticker' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('sector')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>GICS Sector</span>
                          {sortField === 'sector' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th style={{ padding: '8px 10px' }}>Coverage</th>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('observation_date')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>Latest Date</span>
                          {sortField === 'observation_date' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('predicted_return')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>5-Day Forecast</span>
                          {sortField === 'predicted_return' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('signal')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>Signal</span>
                          {sortField === 'signal' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th
                        style={{ padding: '8px 10px', cursor: 'pointer' }}
                        onClick={() => handleSort('forecast_uncertainty')}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span>Uncertainty (&sigma;)</span>
                          {sortField === 'forecast_uncertainty' ? (
                            sortDirection === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                          ) : (
                            <ArrowUpDown size={11} opacity={0.4} />
                          )}
                        </div>
                      </th>
                      <th style={{ padding: '8px 10px' }}>Risk Gate Status</th>
                      <th style={{ padding: '8px 10px', textAlign: 'center' }}>Diagnostics</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageItems.map((c) => {
                      const isSelected = inspectingTicker === c.ticker || selectedTicker === c.ticker;
                      const isBuy = c.signal === 'BUY';
                      const isSell = c.signal === 'SELL';
                      const isHold = c.signal === 'HOLD';
                      const isUnavail = c.signal === 'UNAVAILABLE';

                      return (
                        <tr
                          key={c.ticker}
                          style={{
                            borderBottom: '1px solid var(--border-subtle)',
                            background: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                            cursor: 'pointer',
                          }}
                          onClick={() => handleInspectCompany(c.ticker)}
                          id={`screener-row-${c.ticker}`}
                        >
                          {/* Ticker & Name */}
                          <td style={{ padding: '8px 10px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <strong className="font-mono" style={{ color: 'var(--accent-blue)', fontSize: '12px' }}>
                                {c.ticker}
                              </strong>
                              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                                {c.company_name}
                              </span>
                            </div>
                          </td>

                          {/* Sector */}
                          <td style={{ padding: '8px 10px' }}>
                            <span
                              className="font-mono"
                              style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                borderRadius: '3px',
                                background: 'rgba(255, 255, 255, 0.04)',
                                color: 'var(--text-secondary)',
                                border: '1px solid var(--border-subtle)',
                              }}
                            >
                              {c.sector}
                            </span>
                          </td>

                          {/* Coverage */}
                          <td style={{ padding: '8px 10px' }}>
                            {c.is_truncated ? (
                              <span
                                className="badge-tag badge-offline"
                                title={c.limitations_note || 'Truncated on 2020-04-01'}
                                style={{ fontSize: '9px' }}
                              >
                                <AlertTriangle size={10} />
                                <span>Truncated (86.8%)</span>
                              </span>
                            ) : (
                              <span className="badge-tag badge-status" style={{ fontSize: '9px' }}>
                                Complete (100%)
                              </span>
                            )}
                          </td>

                          {/* Observation Date */}
                          <td style={{ padding: '8px 10px', color: 'var(--text-dim)' }} className="font-mono">
                            {c.observation_date || 'N/A'}
                          </td>

                          {/* Forecast Return */}
                          <td
                            style={{
                              padding: '8px 10px',
                              fontWeight: 700,
                              color: c.predicted_return !== null
                                ? c.predicted_return >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'
                                : 'var(--text-dim)',
                            }}
                            className="font-mono"
                          >
                            {c.predicted_return_pct || 'Unavailable'}
                          </td>

                          {/* Signal */}
                          <td style={{ padding: '8px 10px' }}>
                            <span
                              className="font-mono"
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                padding: '2px 7px',
                                borderRadius: '3px',
                                display: 'inline-block',
                                background: isBuy ? 'rgba(16, 185, 129, 0.15)' : isSell ? 'rgba(244, 63, 94, 0.15)' : isHold ? 'rgba(100, 116, 139, 0.12)' : 'rgba(244, 63, 94, 0.08)',
                                color: isBuy ? 'var(--accent-green)' : isSell ? 'var(--accent-red)' : isHold ? 'var(--text-secondary)' : 'var(--text-dim)',
                                border: `1px solid ${isBuy ? 'var(--accent-green)' : isSell ? 'var(--accent-red)' : 'var(--border-subtle)'}`,
                              }}
                            >
                              {c.signal}
                            </span>
                          </td>

                          {/* Uncertainty */}
                          <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }} className="font-mono">
                            {c.forecast_uncertainty_pct || 'N/A'}
                          </td>

                          {/* Risk Status */}
                          <td style={{ padding: '8px 10px' }}>
                            <span
                              style={{
                                fontSize: '11px',
                                color: c.risk_status.includes('Passed')
                                  ? 'var(--accent-green)'
                                  : c.risk_status.includes('Blocked')
                                  ? 'var(--accent-amber)'
                                  : 'var(--text-dim)',
                              }}
                            >
                              {c.risk_status}
                            </span>
                          </td>

                          {/* Action Button */}
                          <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                            <button
                              type="button"
                              className={`chart-toggle-btn ${isSelected ? 'active' : ''}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleInspectCompany(c.ticker);
                              }}
                              style={{ fontSize: '10px', padding: '3px 8px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                              id={`btn-inspect-${c.ticker}`}
                            >
                              <Eye size={11} />
                              <span>Inspect</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination Controls Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '16px', flexWrap: 'wrap', gap: '10px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                Showing <strong>{startIndex + 1}</strong>&ndash;<strong>{Math.min(startIndex + pageSize, totalItems)}</strong> of <strong>{totalItems}</strong> companies
                {totalItems !== 60 && ` (Filtered from 60 total)`}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Page Size:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  style={{
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border-medium)',
                    color: 'var(--text-primary)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '11px',
                    padding: '3px 6px',
                  }}
                >
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={60}>All 60</option>
                </select>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: '6px' }}>
                  <button
                    type="button"
                    className="chart-toggle-btn"
                    disabled={safePage <= 1}
                    onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                    style={{ padding: '4px 8px' }}
                  >
                    <ChevronLeft size={13} />
                  </button>

                  <span className="font-mono" style={{ fontSize: '11px', padding: '0 8px', color: 'var(--text-primary)' }}>
                    {safePage} / {totalPages}
                  </span>

                  <button
                    type="button"
                    className="chart-toggle-btn"
                    disabled={safePage >= totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                    style={{ padding: '4px 8px' }}
                  >
                    <ChevronRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Excluded Company Audit Card (AA) */}
      <div className="card" style={{ borderLeft: '4px solid var(--accent-red)' }}>
        <div className="card-header">
          <span className="card-title" style={{ color: 'var(--accent-red)' }}>
            <ShieldAlert size={16} />
            <span>Strict Company Identity Policy: AA Exclusion Audit</span>
          </span>
          <span className="badge-tag badge-offline">Permanently Excluded from Research Panel</span>
        </div>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          <strong>Corporate Split Ambiguity:</strong> In November 2016, historical entity <em>Alcoa Inc.</em> executed a corporate separation. The historical corporate shell, SEC CIK (0000004281), and aerospace/engineered products business was renamed to <strong>Arconic Inc. (ARNC)</strong>. Concurrently, the upstream bauxite and aluminum mining business was spun off as a new entity, <strong>Alcoa Corp (AA, CIK 0001675149)</strong>.
          Mapping by the raw ticker string <code className="font-mono" style={{ color: '#fff' }}>"AA"</code> across the pre-2016 and post-2016 boundary blurs two distinct legal entities and violates point-in-time corporate identity invariants. Therefore, AA is strictly excluded from the 60-company research panel until entity intervals are formally resolved.
        </p>
      </div>
    </div>
  );
}
