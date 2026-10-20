import React, { useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import { Sliders, Info, Calendar } from 'lucide-react';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export default function MarketChartsTab({ marketData, selectedTicker, loading, companyMeta }) {
  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [timeRange, setTimeRange] = useState('250'); // Default to ~250 trading days (1 year)

  if (loading) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <p>Loading historical market series for {selectedTicker}...</p>
      </div>
    );
  }

  if (!marketData || !marketData.series || marketData.series.length === 0) {
    return (
      <div className="card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <p>No historical market data available for {selectedTicker}.</p>
      </div>
    );
  }

  // Filter series based on timeRange
  const fullSeries = marketData.series;
  const numPoints = timeRange === 'all' ? fullSeries.length : Math.min(parseInt(timeRange, 10), fullSeries.length);
  const displaySeries = fullSeries.slice(-numPoints);

  const dates = displaySeries.map((p) => p.trading_date);
  const prices = displaySeries.map((p) => p.adjusted_close);
  const volumes = displaySeries.map((p) => p.volume);
  const sma20 = displaySeries.map((p) => p.market_sma_20d);
  const sma50 = displaySeries.map((p) => p.market_sma_50d);
  const rsi = displaySeries.map((p) => p.market_rsi_14d);
  const vol21 = displaySeries.map((p) => (p.market_volatility_21d ? p.market_volatility_21d * 100 : null));

  // Main Price & SMA Chart Data
  const priceDatasets = [
    {
      label: `${selectedTicker} Adjusted Close ($)`,
      data: prices,
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59, 130, 246, 0.08)',
      fill: true,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.1,
    },
  ];

  if (showSMA20) {
    priceDatasets.push({
      label: 'SMA 20-Day',
      data: sma20,
      borderColor: '#f59e0b',
      borderWidth: 1.2,
      borderDash: [3, 3],
      pointRadius: 0,
      fill: false,
    });
  }

  if (showSMA50) {
    priceDatasets.push({
      label: 'SMA 50-Day',
      data: sma50,
      borderColor: '#a855f7',
      borderWidth: 1.2,
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
    });
  }

  const priceChartData = {
    labels: dates,
    datasets: priceDatasets,
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          color: '#94a3b8',
          font: { family: 'Plus Jakarta Sans', size: 11 },
          boxWidth: 12,
        },
      },
      tooltip: {
        backgroundColor: '#0c1017',
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
        borderColor: '#1c2638',
        borderWidth: 1,
        titleFont: { family: 'JetBrains Mono', size: 12 },
        bodyFont: { family: 'JetBrains Mono', size: 11 },
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(28, 38, 56, 0.5)' },
        ticks: {
          color: '#64748b',
          font: { family: 'JetBrains Mono', size: 10 },
          maxTicksLimit: 12,
        },
      },
      y: {
        grid: { color: 'rgba(28, 38, 56, 0.5)' },
        ticks: {
          color: '#64748b',
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (value) => `$${value}`,
        },
      },
    },
  };

  // Volume Chart Data
  const volumeChartData = {
    labels: dates,
    datasets: [
      {
        label: 'Trading Volume',
        data: volumes,
        backgroundColor: 'rgba(59, 130, 246, 0.4)',
        borderColor: 'rgba(59, 130, 246, 0.8)',
        borderWidth: 1,
      },
    ],
  };

  const volumeOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0c1017',
        borderColor: '#1c2638',
        borderWidth: 1,
      },
    },
    scales: {
      x: { display: false },
      y: {
        grid: { color: 'rgba(28, 38, 56, 0.4)' },
        ticks: {
          color: '#64748b',
          font: { family: 'JetBrains Mono', size: 9 },
          callback: (v) => `${(v / 1e6).toFixed(1)}M`,
          maxTicksLimit: 4,
        },
      },
    },
  };

  // RSI & Volatility Chart Data
  const oscChartData = {
    labels: dates,
    datasets: [
      {
        label: 'RSI 14-Day',
        data: rsi,
        borderColor: '#06b6d4',
        borderWidth: 1.2,
        pointRadius: 0,
        yAxisID: 'yRSI',
      },
      {
        label: '21-Day Annualized Volatility (%)',
        data: vol21,
        borderColor: '#f43f5e',
        borderWidth: 1.2,
        pointRadius: 0,
        yAxisID: 'yVol',
      },
    ],
  };

  const oscOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: '#94a3b8',
          font: { size: 10 },
          boxWidth: 10,
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(28, 38, 56, 0.4)' },
        ticks: {
          color: '#64748b',
          font: { family: 'JetBrains Mono', size: 9 },
          maxTicksLimit: 10,
        },
      },
      yRSI: {
        type: 'linear',
        position: 'left',
        min: 0,
        max: 100,
        grid: { color: 'rgba(28, 38, 56, 0.4)' },
        ticks: { color: '#06b6d4', font: { family: 'JetBrains Mono', size: 9 } },
      },
      yVol: {
        type: 'linear',
        position: 'right',
        grid: { drawOnChartArea: false },
        ticks: {
          color: '#f43f5e',
          font: { family: 'JetBrains Mono', size: 9 },
          callback: (v) => `${v}%`,
        },
      },
    },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Notice Banner */}
      <div className="disclaimer-banner">
        <Info size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>PRICE ADJUSTMENT SEMANTICS:</strong> {marketData.adjustment_semantics}.
          All quotes represent verifiable historical daily session aggregates. No fabricated or simulated live feeds are rendered.
        </div>
      </div>

      {/* Main Chart Card */}
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Sliders size={14} />
            <span>
              {selectedTicker} Historical Price & Technical Overlays ({dates[0]} → {dates[dates.length - 1]})
            </span>
          </div>

          <div className="chart-controls">
            {/* Indicator Toggles */}
            <button
              className={`chart-toggle-btn ${showSMA20 ? 'active' : ''}`}
              onClick={() => setShowSMA20(!showSMA20)}
              id="toggle-sma20"
            >
              SMA 20
            </button>
            <button
              className={`chart-toggle-btn ${showSMA50 ? 'active' : ''}`}
              onClick={() => setShowSMA50(!showSMA50)}
              id="toggle-sma50"
            >
              SMA 50
            </button>

            <span style={{ color: 'var(--border-medium)', margin: '0 4px' }}>|</span>

            {/* Time Window Buttons */}
            {['60', '120', '250', '500', 'all'].map((range) => (
              <button
                key={range}
                className={`chart-toggle-btn ${timeRange === range ? 'active' : ''}`}
                onClick={() => setTimeRange(range)}
                id={`btn-range-${range}`}
              >
                {range === 'all' ? 'MAX' : `${range}D`}
              </button>
            ))}
          </div>
        </div>

        <div className="chart-container" style={{ height: '360px' }}>
          <Line data={priceChartData} options={chartOptions} />
        </div>
      </div>

      {/* Secondary Grid: Volume & Technical Oscillators */}
      <div className="terminal-grid">
        <div className="card" style={{ gridColumn: 'span 6' }}>
          <div className="card-header">
            <span className="card-title">Trading Volume (Shares)</span>
            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Source: Tiingo/Yahoo S&P 500 Parquet
            </span>
          </div>
          <div style={{ height: '180px' }}>
            <Bar data={volumeChartData} options={volumeOptions} />
          </div>
        </div>

        <div className="card" style={{ gridColumn: 'span 6' }}>
          <div className="card-header">
            <span className="card-title">RSI (14-Day) & Volatility (21-Day Annualized)</span>
            <span className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Computed on Adjusted Close
            </span>
          </div>
          <div style={{ height: '180px' }}>
            <Line data={oscChartData} options={oscOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
