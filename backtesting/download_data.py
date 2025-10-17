from src.etfs import ETFS
from utils import save_etf_data_yf

if __name__ == "__main__":
    save_etf_data_yf(ETFS+ ["^NSEI"], start="2015-01-01")
