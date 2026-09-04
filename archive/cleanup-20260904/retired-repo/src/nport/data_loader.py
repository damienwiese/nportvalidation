"""Load canonical N-PORT files from a structured fund directory."""

from pathlib import Path

from nport.config import parse_config, parse_filing, parse_holdings
from nport.models import FilingData, FundConfig, Holding


class DataLoader:
    """Read the three canonical inputs used by the XML builder."""

    def __init__(self, fund_dir: str | Path) -> None:
        self._dir = Path(fund_dir)
        if not self._dir.is_dir():
            raise FileNotFoundError(f"Fund directory not found: {self._dir}")

    def load_config(self) -> FundConfig:
        return parse_config(self._dir / "fund_config.txt")

    def load_filing(self, period: str) -> FilingData:
        return parse_filing(self._dir / "filings" / period / "filing_data.txt")

    def load_holdings(self, period: str) -> list[Holding]:
        return parse_holdings(self._dir / "filings" / period / "holdings.csv")

    def load_all(self, period: str) -> tuple[FundConfig, FilingData, list[Holding]]:
        return self.load_config(), self.load_filing(period), self.load_holdings(period)
