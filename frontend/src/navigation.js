/**
 * Navigation and URL synchronization module for Phase 6.6.
 * Provides a single source of truth for tab identifiers, URL mapping,
 * query parameter parsing, serialization, and deterministic state normalization.
 */

export const TAB_TO_URL = Object.freeze({
  overview: 'overview',
  charts: 'market-charts',
  models: 'model-lab',
  prediction: 'prediction-research',
  explorer: 'company-explorer',
});

export const URL_TO_TAB = Object.freeze({
  // Canonical URL query values
  'overview': 'overview',
  'market-charts': 'charts',
  'model-lab': 'models',
  'prediction-research': 'prediction',
  'company-explorer': 'explorer',
  // Backward-compatible internal ID aliases
  'charts': 'charts',
  'models': 'models',
  'prediction': 'prediction',
  'explorer': 'explorer',
});

export const DEFAULT_TAB = 'overview';
export const DEFAULT_TICKER = 'AAPL';

/**
 * Excluded entities that must never be set as active research tickers.
 */
export const EXCLUDED_TICKERS = Object.freeze(['AA']);

/**
 * Parses ticker and tab from a query string, preserving unrelated query parameters.
 * @param {string} searchString - e.g. "?ticker=CAT&tab=market-charts&session=123"
 * @returns {{ ticker: string|null, tab: string, otherParams: URLSearchParams }}
 */
export function parseNavigation(searchString = '') {
  const params = new URLSearchParams(searchString.startsWith('?') ? searchString : `?${searchString}`);
  const rawTicker = params.get('ticker');
  const rawTab = params.get('tab');

  const ticker = rawTicker ? rawTicker.trim().toUpperCase() : null;
  const tab = rawTab && URL_TO_TAB[rawTab.trim().toLowerCase()]
    ? URL_TO_TAB[rawTab.trim().toLowerCase()]
    : DEFAULT_TAB;

  // Clone other params for non-destructive URL updates
  const otherParams = new URLSearchParams(params);
  otherParams.delete('ticker');
  otherParams.delete('tab');

  return { ticker, tab, otherParams };
}

/**
 * Validates a ticker against the loaded canonical capability inventory.
 * @param {string|null} ticker
 * @param {Array} capabilities - Array of company capability objects
 * @returns {{ isValid: boolean, canonicalTicker: string, reason?: string }}
 */
export function validateTicker(ticker, capabilities = []) {
  if (!ticker || typeof ticker !== 'string') {
    return { isValid: false, canonicalTicker: DEFAULT_TICKER, reason: 'Empty or non-string ticker' };
  }

  const normalized = ticker.trim().toUpperCase();

  // Guardrail: Excluded entities
  if (EXCLUDED_TICKERS.includes(normalized)) {
    return {
      isValid: false,
      canonicalTicker: DEFAULT_TICKER,
      reason: `Ticker ${normalized} is strictly excluded by corporate identity policy`,
    };
  }

  // Guardrail: GOOGL share class rejection
  if (normalized === 'GOOGL') {
    return {
      isValid: false,
      canonicalTicker: DEFAULT_TICKER,
      reason: 'GOOGL is not selectable; canonical Class C share is GOOG',
    };
  }

  // If capabilities have loaded, verify presence
  if (capabilities && capabilities.length > 0) {
    const found = capabilities.find(
      (c) => c?.identity?.canonical_ticker === normalized
    );
    if (!found) {
      return {
        isValid: false,
        canonicalTicker: DEFAULT_TICKER,
        reason: `Ticker ${normalized} is not in canonical capability universe`,
      };
    }
  }

  return { isValid: true, canonicalTicker: normalized };
}

/**
 * Builds a normalized URL query string preserving existing non-navigation parameters.
 * @param {string} pathname - e.g. window.location.pathname
 * @param {{ ticker: string, tab: string }} navState
 * @param {string|URLSearchParams} existingSearch - existing query string
 * @returns {string} Fully formatted URL pathname + query string
 */
export function buildNavigationUrl(pathname = '/', { ticker, tab }, existingSearch = '') {
  const currentParams = new URLSearchParams(
    typeof existingSearch === 'string' && existingSearch.startsWith('?')
      ? existingSearch
      : `?${existingSearch}`
  );

  const urlTab = TAB_TO_URL[tab] || TAB_TO_URL[DEFAULT_TAB];
  const urlTicker = (ticker || DEFAULT_TICKER).toUpperCase();

  currentParams.set('ticker', urlTicker);
  currentParams.set('tab', urlTab);

  return `${pathname}?${currentParams.toString()}`;
}

/**
 * Normalizes navigation state against capabilities.
 * @param {string|null} rawTicker
 * @param {string|null} rawTab
 * @param {Array} capabilities
 * @returns {{ ticker: string, tab: string, wasNormalized: boolean }}
 */
export function normalizeState(rawTicker, rawTab, capabilities = []) {
  const resolvedTab = rawTab && URL_TO_TAB[rawTab] ? URL_TO_TAB[rawTab] : DEFAULT_TAB;
  const validation = validateTicker(rawTicker, capabilities);

  const resolvedTicker = validation.isValid ? validation.canonicalTicker : DEFAULT_TICKER;
  const wasNormalized = !validation.isValid || (rawTab && !URL_TO_TAB[rawTab]);

  return {
    ticker: resolvedTicker,
    tab: resolvedTab,
    wasNormalized,
  };
}
