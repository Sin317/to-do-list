import matplotlib.pyplot as plt
import pandas as pd

def plot_stock_performance(stock_data, performance_metrics, ticker):
    """Plots stock price and cumulative returns."""
    if stock_data is None or stock_data.empty:
        return

    plt.figure(figsize=(12, 6))
    plt.plot(stock_data['Close'], label=f'{ticker} Close Price')
    plt.title(f'{ticker} Stock Performance')
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend()
    plt.grid(True)
    plt.show()

    if 'cumulative_return' in performance_metrics:
        plt.figure(figsize=(12, 6))
        plt.plot((1 + stock_data['Close'].pct_change()).cumprod(), label=f'Cumulative Return')
        plt.title(f'{ticker} Cumulative Return')
        plt.xlabel('Date')
        plt.ylabel('Return')
        plt.legend()
        plt.grid(True)
        plt.show()

def plot_spending_by_category(spending_data):
    """Plots spending by category in a pie chart."""
    if not spending_data:
        return

    categories = list(spending_data.keys())
    values = list(spending_data.values())

    plt.figure(figsize=(8, 8))
    plt.pie(values, labels=categories, autopct='%1.1f%%', startangle=140)
    plt.title('Spending by Category')
    plt.show()