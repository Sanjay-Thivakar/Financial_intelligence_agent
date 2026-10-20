"""
SEC EDGAR REST API Client and Fetcher.

Retrieves company submissions and XBRL company facts from data.sec.gov
while strictly enforcing the SEC 10 req/second rate limit and required User-Agent.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from src.config import get_sec_user_agent

logger = logging.getLogger(__name__)


class SECFetcher:
    """Client for SEC EDGAR REST APIs at data.sec.gov."""

    BASE_URL = "https://data.sec.gov"

    def __init__(
        self,
        raw_dir: str = "data/raw/sec",
        user_agent: Optional[str] = None,
        min_request_interval: float = 0.125,  # 8 requests/second to stay safely below 10 req/s limit
    ):
        self.raw_dir = Path(raw_dir)
        self.submissions_dir = self.raw_dir / "submissions"
        self.facts_dir = self.raw_dir / "companyfacts"
        self.submissions_dir.mkdir(parents=True, exist_ok=True)
        self.facts_dir.mkdir(parents=True, exist_ok=True)

        self.user_agent = user_agent or get_sec_user_agent()
        self.min_request_interval = min_request_interval
        self._last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

    def _throttle(self) -> None:
        """Enforces rate limit interval between consecutive calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_time = time.time()

    def fetch_submissions(self, cik: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches submissions metadata JSON for a 10-digit zero-padded CIK."""
        cik_clean = str(cik).strip().zfill(10)
        cache_file = self.submissions_dir / f"CIK{cik_clean}.json"

        if cache_file.exists() and not force_refresh:
            logger.debug(f"Loading cached submissions for CIK {cik_clean} from {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/submissions/CIK{cik_clean}.json"
        self._throttle()

        logger.info(f"Fetching SEC submissions for CIK {cik_clean} from {url}")
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            logger.warning(f"CIK {cik_clean} not found on SEC EDGAR (HTTP 404)")
            return {}
        resp.raise_for_status()

        data = resp.json()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data

    def fetch_submission_file(self, filename: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches and caches an older paginated submissions file (e.g. CIK0001652044-submissions-001.json)."""
        cache_file = self.submissions_dir / filename
        if cache_file.exists() and not force_refresh:
            logger.debug(f"Loading cached submission file {filename} from {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/submissions/{filename}"
        self._throttle()

        logger.info(f"Fetching SEC submission file {filename} from {url}")
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            logger.warning(f"Submission file {filename} not found on SEC EDGAR (HTTP 404)")
            return {}
        resp.raise_for_status()

        data = resp.json()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return data

    def fetch_submissions_with_history(
        self,
        cik: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches submissions for a CIK, including any paginated older submission files
        whose date intervals intersect [start_date, end_date].
        Returns a list of submission dictionaries (primary recent dict + any paginated dicts).
        """
        primary = self.fetch_submissions(cik, force_refresh=force_refresh)
        if not primary:
            return []

        results = [primary]
        if not start_date and not end_date:
            return results

        files = primary.get("filings", {}).get("files", [])
        for file_info in files:
            f_name = file_info.get("name")
            f_from = file_info.get("filingFrom")
            f_to = file_info.get("filingTo")

            # Check for date overlap
            overlaps = True
            if start_date and f_to and f_to < start_date:
                overlaps = False
            if end_date and f_from and f_from > end_date:
                overlaps = False

            if overlaps and f_name:
                paged_data = self.fetch_submission_file(f_name, force_refresh=force_refresh)
                if paged_data:
                    results.append(paged_data)

        return results

    def fetch_company_facts(self, cik: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches all XBRL company facts JSON for a 10-digit zero-padded CIK."""
        cik_clean = str(cik).strip().zfill(10)
        cache_file = self.facts_dir / f"CIK{cik_clean}.json"

        if cache_file.exists() and not force_refresh:
            logger.debug(f"Loading cached company facts for CIK {cik_clean} from {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik_clean}.json"
        self._throttle()

        logger.info(f"Fetching SEC company facts for CIK {cik_clean} from {url}")
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            logger.warning(f"No XBRL facts found for CIK {cik_clean} (HTTP 404)")
            return {}
        resp.raise_for_status()

        data = resp.json()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data
