import sqlite3
import os
import datetime
import json
import random

def process_data(user_input, filename="data.json"):
    """
    A more complex function with added features, but still lacking proper design and security.
    """
    try:
        # JSON file operations (still basic)
        data = []
        if os.path.exists(filename):
            with open(filename, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    pass 

        data.append({
            "input": user_input,
            "timestamp": datetime.datetime.now().isoformat(),
            "random_number": random.randint(1, 100)
        })

        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

        # Database operations (SQL injection still present)
        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()

        cursor.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, value TEXT, created_at TEXT)")

        cursor.execute(f"INSERT INTO items (value, created_at) VALUES ('{user_input}', '{datetime.datetime.now().isoformat()}')")

        cursor.execute("SELECT * FROM items")
        results = cursor.fetchall()
        print(f"Database results: {results}")

        # Adding a fake "API" call simulation (no actual network)
        if random.random() < 0.5: #simulate a 50% chance of success
            api_response = {"status": "success", "message": f"Processed: {user_input}"}
        else:
            api_response = {"status":"failure", "message": "API call failed"}

        print(f"API Simulation: {api_response}")

        conn.commit()
        conn.close()

        # More data manipulation (with more complex logic)
        data_list = user_input.split()
        processed_list = []
        for item in data_list:
            if item.isdigit():
                num = int(item)
                if num % 2 == 0:
                    processed_list.append(num * 3)
                else:
                    processed_list.append(num + 5)
            else:
                processed_list.append(item.lower() if random.random() < 0.5 else item.upper())

        print(f"Processed data: {processed_list}")

        # Adding a simple file backup mechanism (still very basic)
        if random.random() < 0.2: #simulate a 20% chance of backing up
            backup_filename = f"backup_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            try:
                with open(filename, "r") as src, open(backup_filename, "w") as dest:
                    dest.write(src.read())
                print(f"Backup created: {backup_filename}")
            except Exception as backup_err:
                print(f"Backup failed: {backup_err}")

        # Inconsistent return types.
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