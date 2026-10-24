import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  TAB_TO_URL,
  URL_TO_TAB,
  DEFAULT_TAB,
  DEFAULT_TICKER,
  parseNavigation,
  validateTicker,
  buildNavigationUrl,
  normalizeState,
} from './navigation.js';

test('TAB_TO_URL maps internal tab identifiers to URL values', () => {
  assert.equal(TAB_TO_URL.overview, 'overview');
  assert.equal(TAB_TO_URL.charts, 'market-charts');
  assert.equal(TAB_TO_URL.models, 'model-lab');
  assert.equal(TAB_TO_URL.prediction, 'prediction-research');
  assert.equal(TAB_TO_URL.explorer, 'company-explorer');
});

test('URL_TO_TAB correctly resolves valid URL query values', () => {
  assert.equal(URL_TO_TAB['overview'], 'overview');
  assert.equal(URL_TO_TAB['market-charts'], 'charts');
  assert.equal(URL_TO_TAB['model-lab'], 'models');
  assert.equal(URL_TO_TAB['prediction-research'], 'prediction');
  assert.equal(URL_TO_TAB['company-explorer'], 'explorer');
});

test('URL_TO_TAB supports internal ID aliases for backward compatibility', () => {
  assert.equal(URL_TO_TAB['charts'], 'charts');
  assert.equal(URL_TO_TAB['models'], 'models');
  assert.equal(URL_TO_TAB['prediction'], 'prediction');
  assert.equal(URL_TO_TAB['explorer'], 'explorer');
});

test('parseNavigation parses valid ticker and tab query parameters', () => {
  const result = parseNavigation('?ticker=CAT&tab=market-charts');
  assert.equal(result.ticker, 'CAT');
  assert.equal(result.tab, 'charts');
});

test('parseNavigation defaults unknown tab to overview', () => {
  const result = parseNavigation('?ticker=MSFT&tab=unknown-tab');
  assert.equal(result.ticker, 'MSFT');
  assert.equal(result.tab, DEFAULT_TAB);
});

test('parseNavigation normalizes ticker to uppercase', () => {
  const result = parseNavigation('?ticker=nvda&tab=model-lab');
  assert.equal(result.ticker, 'NVDA');
  assert.equal(result.tab, 'models');
});

test('parseNavigation preserves unrelated query parameters', () => {
  const result = parseNavigation('?ticker=JPM&tab=prediction-research&model=ridge&view=table');
  assert.equal(result.ticker, 'JPM');
  assert.equal(result.tab, 'prediction');
  assert.equal(result.otherParams.get('model'), 'ridge');
  assert.equal(result.otherParams.get('view'), 'table');
  assert.equal(result.otherParams.has('ticker'), false);
  assert.equal(result.otherParams.has('tab'), false);
});

test('buildNavigationUrl constructs shareable URL preserving other parameters', () => {
  const url = buildNavigationUrl('/', { ticker: 'CAT', tab: 'charts' }, 'theme=dark&mode=pro');
  assert.ok(url.includes('ticker=CAT'));
  assert.ok(url.includes('tab=market-charts'));
  assert.ok(url.includes('theme=dark'));
  assert.ok(url.includes('mode=pro'));
});

test('validateTicker rejects excluded AA entity', () => {
  const mockCapabilities = [
    { identity: { canonical_ticker: 'AAPL' } },
    { identity: { canonical_ticker: 'CAT' } },
  ];
  const res = validateTicker('AA', mockCapabilities);
  assert.equal(res.isValid, false);
  assert.equal(res.canonicalTicker, DEFAULT_TICKER);
  assert.match(res.reason, /excluded/i);
});

test('validateTicker rejects GOOGL and suggests canonical GOOG', () => {
  const mockCapabilities = [
    { identity: { canonical_ticker: 'AAPL' } },
    { identity: { canonical_ticker: 'GOOG' } },
  ];
  const res = validateTicker('GOOGL', mockCapabilities);
  assert.equal(res.isValid, false);
  assert.equal(res.canonicalTicker, DEFAULT_TICKER);
  assert.match(res.reason, /GOOG/);
});

test('validateTicker accepts valid prototype and expanded cohort tickers', () => {
  const mockCapabilities = [
    { identity: { canonical_ticker: 'AAPL' } },
    { identity: { canonical_ticker: 'CAT' } },
    { identity: { canonical_ticker: 'MSFT' } },
  ];
  assert.equal(validateTicker('AAPL', mockCapabilities).isValid, true);
  assert.equal(validateTicker('CAT', mockCapabilities).isValid, true);
  assert.equal(validateTicker('cat', mockCapabilities).isValid, true);
  assert.equal(validateTicker('MSFT', mockCapabilities).isValid, true);
});

test('validateTicker rejects unknown ticker not present in capability cohort', () => {
  const mockCapabilities = [
    { identity: { canonical_ticker: 'AAPL' } },
    { identity: { canonical_ticker: 'CAT' } },
  ];
  const res = validateTicker('UNKNOWN_XYZ', mockCapabilities);
  assert.equal(res.isValid, false);
  assert.equal(res.canonicalTicker, DEFAULT_TICKER);
});

test('normalizeState recovers invalid ticker and tab deterministically', () => {
  const mockCapabilities = [{ identity: { canonical_ticker: 'AAPL' } }];
  const state = normalizeState('INVALID_TICKER', 'non-existent-tab', mockCapabilities);
  assert.equal(state.ticker, DEFAULT_TICKER);
  assert.equal(state.tab, DEFAULT_TAB);
  assert.equal(state.wasNormalized, true);
});
