import sqlite3
import os

def process_data(user_input, filename="data.txt"):
    """
    It reads, writes, and performs SQL queries with user input directly.
    """

    try:
        # File operations 
        if os.path.exists(filename):
            with open(filename, "r") as f:
                file_content = f.read()
                print(f"File content: {file_content}")

        with open(filename, "a") as f:
            f.write(user_input + "\n")

        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()

        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT)")

        cursor.execute(f"INSERT INTO users (name) VALUES ('{user_input}')")

        cursor.execute("SELECT * FROM users")
        results = cursor.fetchall()
        print(f"Database results: {results}")

        conn.commit()
        conn.close()

        data_list = user_input.split()
        processed_list = []
        for item in data_list:
            if item.isdigit():
                processed_list.append(int(item) * 2)
            else:
                processed_list.append(item.upper())

        print(f"Processed data: {processed_list}")

        if len(processed_list) > 5:
            return processed_list
        else:
            return "Processed data is short."

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def main():
    """
    Main function to get user input and call process_data.
    """
    user_input = input("Enter some data: ")
    result = process_data(user_input)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()