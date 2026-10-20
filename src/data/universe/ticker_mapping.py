"""
Ticker mapping, normalization, and historical SEC CIK resolution module.

Handles:
- Normalization of ticker formats (e.g. BRK-B <-> BRK.B, BF-B <-> BF.B).
- Tracking ticker transitions (e.g. FB -> META, CDAY -> DAY, ANTM -> ELV).
- Historical CIK registry for delisted/acquired historical constituents.
- Canonical Company ID generation.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple


def normalize_ticker(symbol: str) -> str:
    """Normalize ticker symbol to standard US equity dot notation.

    Converts hyphens to dots (e.g. 'BRK-B' -> 'BRK.B', 'BF-B' -> 'BF.B')
    and strips whitespace while maintaining upper case.
    """
    if not symbol or not isinstance(symbol, str):
        return ""
    clean = symbol.strip().upper()
    # Replace hyphen with dot for share classes
    clean = re.sub(r"-([A-Za-z])$", r".\1", clean)
    clean = re.sub(r"/([A-Za-z])$", r".\1", clean)
    return clean


def format_cik(cik: Optional[int | str]) -> Optional[str]:
    """Format CIK as 10-digit zero-padded string compliant with SEC EDGAR standard.

    Returns None if CIK is None, NaN, empty, or unparseable.
    """
    if cik is None:
        return None
    s = str(cik).strip()
    if not s or s.lower() in ("nan", "none", "null", "0", ""):
        return None
    # Strip any decimal point if read as float string (e.g. '320193.0')
    if "." in s:
        s = s.split(".")[0]
    # Digits only
    digits = re.sub(r"\D", "", s)
    if not digits or int(digits) == 0:
        return None
    return digits.zfill(10)


def generate_company_id(cik: Optional[str], canonical_name: str, fallback_ticker: str) -> str:
    """Generate a stable canonical company identifier.

    - If CIK is available: 'US_CIK_<10-digit-cik>'
    - If CIK is not available: 'COMP_NO_CIK_<clean_ticker>'
    """
    if cik:
        formatted = format_cik(cik)
        if formatted:
            return f"US_CIK_{formatted}"
    clean_t = normalize_ticker(fallback_ticker)
    clean_t = re.sub(r"[^A-Z0-9]", "_", clean_t)
    return f"COMP_NO_CIK_{clean_t}"


# Explicit verified historical S&P 500 ticker changes (predecessor -> successor)
TICKER_SUCCESSIONS: Dict[str, str] = {
    "FB": "META",
    "CDAY": "DAY",
    "WLTW": "WTW",
    "ANTM": "ELV",
    "ANT": "ANTM",
    "ABC": "COR",
    "PKI": "RVTY",
    "FBHS": "FBIN",
    "VIAC": "PARA",
    "VIAB": "PARA",
    "RTN": "RTX",
    "Q": "IQV",
    "DPS": "KDP",
    "SYMC": "GEN",
    "NLOK": "GEN",
    "CTL": "LUMN",
    "BLL": "BALL",
    "FLT": "CPAY",
    "RE": "EG",
    "DISCA": "WBD",
    "DISCK": "WBD",
    "TWX": "T",  # Acquired by AT&T
    "MON": "BAYRY",  # Acquired by Bayer
    "CELG": "BMY",  # Acquired by Bristol Myers
    "AET": "CVS",  # Acquired by CVS
    "ALXN": "AZN",  # Acquired by AstraZeneca
    "APC": "OXY",  # Acquired by Occidental
    "DRE": "PLD",  # Acquired by Prologis
    "INFO": "SPGI",  # Acquired by S&P Global
    "CERN": "ORCL",  # Acquired by Oracle
    "XLNX": "AMD",  # Acquired by AMD
    "ESRX": "CI",  # Acquired by Cigna
    "MYL": "VTRS",  # Merged into Viatris
    "VAR": "SHL",  # Acquired by Siemens Healthineers
    "MXIM": "ADI",  # Acquired by Analog Devices
    "CXO": "COP",  # Acquired by ConocoPhillips
    "TIF": "MC",  # Acquired by LVMH
    "ETFC": "MS",  # Acquired by Morgan Stanley
    "AGN": "ABBV",  # Acquired by AbbVie
    "BBT": "TFC",  # Merged to form Truist
    "STI": "TFC",  # Merged to form Truist
    "UTX": "RTX",  # Merged to form RTX
}

# Curated SEC EDGAR CIK mappings for major historical / delisted S&P 500 constituents
HISTORICAL_CIK_LOOKUP: Dict[str, Tuple[str, str, Optional[str]]] = {
    # Ticker: (CIK, Canonical Company Name, Sector)
    "AABA": ("0001011006", "Altaba Inc. (formerly Yahoo! Inc.)", "Communication Services"),
    "YHOO": ("0001011006", "Yahoo! Inc.", "Communication Services"),
    "AAMRQ": ("0000004515", "AMR Corporation (American Airlines)", "Industrials"),
    "AMR": ("0000004515", "AMR Corporation", "Industrials"),
    "ABC": ("0001140859", "AmerisourceBergen Corp (now Cencora)", "Health Care"),
    "ABMD": ("0000815094", "ABIOMED Inc.", "Health Care"),
    "AET": ("0001122304", "Aetna Inc.", "Health Care"),
    "AGN": ("0001578845", "Allergan plc", "Health Care"),
    "AKS": ("0001089970", "AK Steel Holding Corp", "Materials"),
    "ALXN": ("0000899866", "Alexion Pharmaceuticals, Inc.", "Health Care"),
    "ANTM": ("0001156039", "Anthem, Inc. (now Elevance Health)", "Health Care"),
    "APC": ("0000773910", "Anadarko Petroleum Corp", "Energy"),
    "BBBY": ("0000886158", "Bed Bath & Beyond Inc.", "Consumer Discretionary"),
    "CELG": ("0000816284", "Celgene Corp", "Health Care"),
    "CERN": ("0000804753", "Cerner Corporation", "Health Care"),
    "CHK": ("0000895126", "Chesapeake Energy Corporation", "Energy"),
    "CIT": ("0001171825", "CIT Group Inc.", "Financials"),
    "CLX": ("0000021076", "Clorox Co", "Consumer Staples"),
    "CMCSK": ("0001166691", "Comcast Corp (Class A Special)", "Communication Services"),
    "CPQ": ("0000709073", "Compaq Computer Corp", "Information Technology"),
    "CTL": ("0000018926", "CenturyLink, Inc. (now Lumen)", "Communication Services"),
    "CBE": ("0000024491", "Cooper Industries plc", "Industrials"),
    "DISCA": ("0001437107", "Discovery, Inc. (Series A)", "Communication Services"),
    "DISCK": ("0001437107", "Discovery, Inc. (Series C)", "Communication Services"),
    "DOW": ("0000029915", "The Dow Chemical Company (historical)", "Materials"),
    "DPS": ("0001418135", "Dr Pepper Snapple Group, Inc.", "Consumer Staples"),
    "DRE": ("0000783280", "Duke Realty Corp", "Real Estate"),
    "DWDP": ("0001666700", "DowDuPont Inc.", "Materials"),
    "ENE": ("0001024401", "Enron Corp", "Energy"),
    "ENRNQ": ("0001024401", "Enron Corp", "Energy"),
    "ESRX": ("0001532063", "Express Scripts Holding Co", "Health Care"),
    "FB": ("0001326801", "Meta Platforms, Inc. (formerly Facebook)", "Communication Services"),
    "FBHS": ("0001519751", "Fortune Brands Home & Security, Inc.", "Industrials"),
    "FLIR": ("0000354908", "FLIR Systems, Inc.", "Information Technology"),
    "FOSL": ("0000883569", "Fossil Group, Inc.", "Consumer Discretionary"),
    "FRX": ("0000949158", "Forest Laboratories, Inc.", "Health Care"),
    "FTR": ("0000020520", "Frontier Communications Corp", "Communication Services"),
    "HCBK": ("0001109525", "Hudson City Bancorp, Inc.", "Financials"),
    "INFO": ("0001598014", "IHS Markit Ltd.", "Financials"),
    "JCP": ("0000076267", "J. C. Penney Company, Inc.", "Consumer Discretionary"),
    "KFT": ("0001103982", "Kraft Foods Inc. (historical)", "Consumer Staples"),
    "LEH": ("0000806085", "Lehman Brothers Holdings Inc.", "Financials"),
    "LEHMQ": ("0000806085", "Lehman Brothers Holdings Inc.", "Financials"),
    "LLTC": ("0000789073", "Linear Technology Corp", "Information Technology"),
    "LNKD": ("0001271024", "LinkedIn Corp", "Communication Services"),
    "LO": ("0001442145", "Lorillard, Inc.", "Consumer Staples"),
    "LUK": ("0000096223", "Leucadia National Corp", "Financials"),
    "MHS": ("0000885639", "Medco Health Solutions, Inc.", "Health Care"),
    "MON": ("0001110783", "Monsanto Co", "Materials"),
    "MYL": ("0001623613", "Mylan N.V.", "Health Care"),
    "NBL": ("0000072207", "Noble Energy, Inc.", "Energy"),
    "NE": ("0000072137", "Noble Corporation plc", "Energy"),
    "PBI": ("0000078814", "Pitney Bowes Inc.", "Industrials"),
    "PCLN": ("0001075531", "The Priceline Group Inc. (now Booking)", "Consumer Discretionary"),
    "PCP": ("0000079879", "Precision Castparts Corp.", "Industrials"),
    "PKI": ("0000031235", "PerkinElmer, Inc. (now Revvity)", "Health Care"),
    "PX": ("0000884905", "Praxair, Inc.", "Materials"),
    "Q": ("0001478242", "QuintilesIMS (now IQVIA)", "Health Care"),
    "QEP": ("0001483830", "QEP Resources, Inc.", "Energy"),
    "RHT": ("0001087423", "Red Hat, Inc.", "Information Technology"),
    "RTN": ("0000101829", "Raytheon Company (historical)", "Industrials"),
    "S": ("0000101830", "Sprint Corp / Sprint Nextel", "Communication Services"),
    "SE": ("0001372784", "Spectra Energy Corp", "Energy"),
    "SHLD": ("0001314428", "Sears Holdings Corp", "Consumer Discretionary"),
    "SHLDQ": ("0001314428", "Sears Holdings Corp", "Consumer Discretionary"),
    "SIAL": ("0000090185", "Sigma-Aldrich Corp", "Materials"),
    "SNDK": ("0001000180", "SanDisk Corp", "Information Technology"),
    "SPLS": ("0000874716", "Staples, Inc.", "Consumer Discretionary"),
    "STI": ("0000750556", "SunTrust Banks, Inc.", "Financials"),
    "STJ": ("0000086266", "St. Jude Medical, Inc.", "Health Care"),
    "SWY": ("0000086144", "Safeway Inc.", "Consumer Staples"),
    "SYMC": ("0000849399", "Symantec Corp (now Gen Digital)", "Information Technology"),
    "TIF": ("0000098246", "Tiffany & Co.", "Consumer Discretionary"),
    "TWX": ("0001105705", "Time Warner Inc.", "Communication Services"),
    "TXT": ("0000217346", "Textron Inc.", "Industrials"),
    "UTX": ("0000101829", "United Technologies Corp", "Industrials"),
    "VAR": ("0000203527", "Varian Medical Systems, Inc.", "Health Care"),
    "VIAB": ("0000813828", "Viacom Inc. (Class B)", "Communication Services"),
    "VIAC": ("0000813828", "ViacomCBS Inc.", "Communication Services"),
    "WFM": ("0000865436", "Whole Foods Market, Inc.", "Consumer Staples"),
    "WLTW": ("0001140536", "Willis Towers Watson plc", "Financials"),
    "WYN": ("0001361658", "Wyndham Worldwide Corp", "Consumer Discretionary"),
    "XL": ("0001060349", "XL Group Ltd", "Financials"),
    "XLNX": ("0000743988", "Xilinx, Inc.", "Information Technology"),
    "BSC": ("0000777001", "The Bear Stearns Companies Inc.", "Financials"),
    "MER": ("0000065100", "Merrill Lynch & Co., Inc.", "Financials"),
    "WB": ("0000072695", "Wachovia Corporation", "Financials"),
    "TYC": ("0000833444", "Tyco International plc", "Industrials"),
    "KMG": ("0000055785", "Kerr-McGee Corporation", "Energy"),
    "BLS": ("0000732712", "BellSouth Corporation", "Communication Services"),
    "PD": ("0000077920", "Phelps Dodge Corp", "Materials"),
    "PGL": ("0000077384", "Peoples Energy Corp", "Utilities"),
    "ANDW": ("0000006769", "Andrew Corp", "Information Technology"),
    "DJ": ("0000029924", "Dow Jones & Company, Inc.", "Communication Services"),
    "CEN": ("0001109354", "Ceridian Corp (pre-2007)", "Industrials"),
    "TEK": ("0000096793", "Tektronix, Inc.", "Information Technology"),
    "TXU": ("0001023844", "TXU Corp (Energy Future Holdings)", "Utilities"),
    "FDC": ("0000883980", "First Data Corporation (historical)", "Financials"),
    "BOL": ("0000012222", "Bausch & Lomb Inc.", "Health Care"),
    "HLT": ("0000047580", "Hilton Hotels Corp (pre-LBO)", "Consumer Discretionary"),
    "BMET": ("0000011388", "Biomet, Inc.", "Health Care"),
    "RYI": ("0000086207", "Ryerson Tull, Inc.", "Materials"),
    "SRR": ("0000887730", "Stride Rite Corp", "Consumer Discretionary"),
    "KATE": ("0000352363", "Kate Spade & Company", "Consumer Discretionary"),
    "BCR": ("0000009223", "C.R. Bard, Inc.", "Health Care"),
    "TNB": ("0000098222", "Thomas & Betts Corp", "Industrials"),
    "GR": ("0000042888", "Goodrich Corp", "Industrials"),
    "PGN": ("0001094093", "Progress Energy, Inc.", "Utilities"),
    "SUN": ("0000095304", "Sunoco, Inc. (historical)", "Energy"),
    "CEG": ("0001004440", "Constellation Energy Group (pre-Exelon)", "Utilities"),
    "GAS": ("0001004155", "AGL Resources Inc.", "Utilities"),
    "ACV": ("0000002230", "Alberto-Culver Co", "Consumer Staples"),
    "MEE": ("0000106640", "Massey Energy Co", "Energy"),
    "NSM": ("0000070530", "National Semiconductor Corp", "Information Technology"),
    "NOVL": ("0000758004", "Novell, Inc.", "Information Technology"),
    "JAVA": ("0000709519", "Sun Microsystems, Inc.", "Information Technology"),
    "COMS": ("0000738076", "3Com Corporation", "Information Technology"),
    "BDK": ("0000012927", "Black & Decker Corp", "Industrials"),
    "BNI": ("0000934612", "Burlington Northern Santa Fe Corp", "Industrials"),
    "MIL": ("0000066570", "Millipore Corp", "Health Care"),
    "SII": ("0000885275", "Smith International, Inc.", "Energy"),
    "WYE": ("0000005513", "Wyeth (American Home Products)", "Health Care"),
    "CTX": ("0000020359", "Centex Corp", "Consumer Discretionary"),
    "SGP": ("0000087508", "Schering-Plough Corp", "Health Care"),
    "ROH": ("0000084792", "Rohm and Haas Co", "Materials"),
    "UST": ("0000101884", "UST Inc.", "Consumer Staples"),
    "BUD": ("0000006348", "Anheuser-Busch Companies, Inc.", "Consumer Staples"),
    "NCC": ("0000070684", "National City Corp", "Financials"),
    "WWY": ("0000109590", "Wm. Wrigley Jr. Company", "Consumer Staples"),
    "SAF": ("0000086088", "SAFECO Corp", "Financials"),
    "HPC": ("0000047217", "Hercules Inc.", "Materials"),
    "IKN": ("0000803562", "IKON Office Solutions, Inc.", "Industrials"),
    "LDG": ("0000866048", "Longs Drug Stores Corp", "Consumer Staples"),
}
