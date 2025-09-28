from src.etfs import ETFS
from src.utils import save_etf_data

if __name__ == "__main__":
    save_etf_data(ETFS, start="2015-01-01")
