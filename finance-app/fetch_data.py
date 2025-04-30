import yfinance as yf
import pandas as pd

def fetch_stock_data(ticker, start_date, end_date):
    """Fetches stock data from yfinance."""
    try:
        data = yf.download(ticker, start=start_date, end=end_date)
        return data
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return None

def fetch_transaction_data(filepath):
    """Fetches transaction data from a CSV file."""
    try:
        data = pd.read_csv(filepath)
        return data
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return None
    except Exception as e:
        print(f"Error reading transaction data: {e}")
        return None