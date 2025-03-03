import pandas as pd

def calculate_stock_performance(stock_data):
    """Calculates stock performance metrics."""
    if stock_data is None or stock_data.empty:
        return {}

    daily_returns = stock_data['Close'].pct_change().dropna()
    average_return = daily_returns.mean()
    std_deviation = daily_returns.std()
    return {
        'average_return': average_return,
        'std_deviation': std_deviation,
        'cumulative_return': (1 + daily_returns).cumprod()[-1] - 1,
    }

def categorize_transactions(transaction_data):
    """Categorizes transactions based on description."""
    if transaction_data is None or transaction_data.empty:
        return pd.DataFrame()

    def categorize(description):
        description = str(description).lower()
        if "grocery" in description or "food" in description:
            return "Groceries"
        elif "restaurant" in description or "dine" in description:
            return "Dining"
        elif "amazon" in description or "online" in description:
            return "Shopping"
        elif "netflix" in description or "spotify" in description:
            return "Subscriptions"
        elif "salary" in description or "deposit" in description:
            return "Income"
        else:
            return "Other"

    transaction_data['Category'] = transaction_data['Description'].apply(categorize)
    return transaction_data