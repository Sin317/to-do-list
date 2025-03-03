from app.data_fetcher import fetch_stock_data, fetch_transaction_data
from app.analysis import calculate_stock_performance, categorize_transactions, calculate_spending_by_category
from app.visualization import plot_stock_performance, plot_spending_by_category

def main():
    ticker = "AAPL"
    start_date = "2023-01-01"
    end_date = "2023-12-31"
    transaction_filepath = "transactions.csv" #Replace with your transaction file

    stock_data = fetch_stock_data(ticker, start_date, end_date)
    performance_metrics = calculate_stock_performance(stock_data)
    plot_stock_performance(stock_data, performance_metrics, ticker)

    transaction_data = fetch_transaction_data(transaction_filepath)
    categorized_transactions = categorize_transactions(transaction_data)
    spending_data = calculate_spending_by_category(categorized_transactions)
    plot_spending_by_category(spending_data)

if __name__ == "__main__":
    main()