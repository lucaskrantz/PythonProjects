import concurrent.futures
import requests
from bs4 import BeautifulSoup
import sqlite3
import logging
import csv
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import textwrap

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Authentication and Setup for Google Sheets
# def authenticate_google_sheets(credentials_file='credentials.json'):
#     absolute_path = "/Users/lucas/PythonProjects/credentials.json"
#     scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
#     creds = ServiceAccountCredentials.from_json_keyfile_name(absolute_path, scope)
#     client = gspread.authorize(creds)
#     return client

# def export_data_to_google_sheets(connection, sheet_name, credentials_file='/Users/lucas/PythonProjects/credentials.json', share_email=None):
#     client = authenticate_google_sheets(credentials_file)
    
#     try:
#         # Try to open the existing Google Sheet
#         sheet = client.open(sheet_name).sheet1
#     except gspread.exceptions.SpreadsheetNotFound:
#         # Create a new Google Sheet if it doesn't exist
#         sheet = client.create(sheet_name).sheet1
    
#     cursor = connection.cursor()
#     cursor.execute("SELECT title, price, link, description FROM products")
#     rows = cursor.fetchall()
    
#     # Prepare the data for Google Sheets
#     df = pd.DataFrame(rows, columns=['Title', 'Price', 'Link', 'Description'])
    
#     # Clear the existing content in the sheet
#     sheet.clear()

#     # Write the DataFrame to Google Sheets
#     sheet.update([df.columns.values.tolist()] + df.values.tolist())

#     # Get the URL of the Google Sheet
#     sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet.spreadsheet.id}/edit"
#     logging.info(f"Data exported to Google Sheets: {sheet_name} successfully.")
#     print(f"Data exported to Google Sheets: {sheet_name} successfully.")
#     print(f"View the sheet at: {sheet_url}")  # Print the URL for easy access

#     # Share the Google Sheet with a specified email if provided
#     if share_email:
#         sheet.share(share_email, perm_type='user', role='writer')
#         logging.info(f"Google Sheet shared with: {share_email}")
#         print(f"Google Sheet shared with: {share_email}")




def product_exists(connection, link):
    cursor = connection.cursor()
    cursor.execute("SELECT 1 FROM products WHERE link = ?", (link,))
    return cursor.fetchone() is not None

# Function to get product data

def remove_duplicates(connection):
    cursor = connection.cursor()
    
    # Find duplicates based on the normalized (lowercase, stripped) link
    cursor.execute('''
        WITH DuplicateLinks AS (
            SELECT 
                id, 
                LOWER(TRIM(link)) AS normalized_link,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(TRIM(link)) 
                    ORDER BY id
                ) AS rn
            FROM products
        )
        SELECT id, normalized_link FROM DuplicateLinks WHERE rn > 1
    ''')
    rows = cursor.fetchall()

    logging.info(f"Found {len(rows)} duplicate entries by link.")

    if rows:
        duplicates = [row[0] for row in rows]
        logging.info(f"Duplicate IDs to remove: {duplicates}")

        cursor.executemany('DELETE FROM products WHERE id = ?', [(id,) for id in duplicates])
        connection.commit()

    return len(rows)

def get_product_data(session, url):
    logging.info(f"Fetching product data from {url}")
    try:
        product_page = session.get(url)
        product_page.raise_for_status()
        product_soup = BeautifulSoup(product_page.content, "html.parser")
        
        desc_tag = product_soup.find('div', class_='product-single__description rte')
        desc_text = desc_tag.text.strip() if desc_tag else None
        return desc_text
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None

def clean_database_prices(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT id, price FROM products")
    rows = cursor.fetchall()

    for row in rows:
        id_, price = row
        # Normalize the price by removing 'kr', commas, and spaces
        normalized_price = price.replace('kr', '').replace(',', '').replace(' ', '').strip()
        cursor.execute('UPDATE products SET price = ? WHERE id = ?', (normalized_price, id_))
    
    connection.commit()
    logging.info(f"Cleaned {len(rows)} price entries in the database.")


def export_data_to_csv(connection, filename='scraped_data.csv'):
    # Ensure the filename ends with .csv
    if not filename.endswith('.csv'):
        filename += '.csv'

    # Create the specified directory if it doesn't exist
    directory = os.path.dirname(filename)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    cursor = connection.cursor()
    cursor.execute("SELECT title, price, link, description FROM products")
    rows = cursor.fetchall()

    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Title', 'Price (kr)', 'Link', 'Description']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)

        writer.writeheader()
        for row in rows:
            writer.writerow({
                'Title': row[0].strip(),
                'Price (kr)': row[1].strip(),
                'Link': row[2].strip(),
                'Description': ensure_wrappable(row[3].strip() if row[3] else '')
            })

    logging.info(f"Data exported to {filename} successfully.")
    print(f"Data exported to {filename} successfully.")  # Additional feedback for the user

def ensure_wrappable(description, width=80):
    """
    Ensure the description is formatted to be easily wrappable within a set width.
    """
    wrapped_description = textwrap.fill(description, width=width)
    return wrapped_description




# Function to scrape element data

def scrape_element(session, element):
    title_element = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    price_element = element.find("span", class_="price-item price-item--regular")
    link_url = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")["href"]

    # Normalize price by stripping 'kr', commas, spaces, and any additional whitespace
    price_text = price_element.text.replace('kr', '').replace(',', '').replace(' ', '').strip()

    prod_desc = get_product_data(session, f"https://jus.se{link_url}")
    
    return {
        "title": title_element.text.strip(),
        "price": price_text,
        "link": f"https://jus.se{link_url}",
        "description": prod_desc
    }


def scrape_data():
    URL = "https://jus.se/collections/all-menswear/men"
    
    try:
        with requests.Session() as session:
            main_page = session.get(URL)
            main_page.raise_for_status()
            soup = BeautifulSoup(main_page.content, "html.parser")
            results = soup.find(id="PageContainer")
            elements = results.find_all("div", class_="grid-view-item product-card")

            with concurrent.futures.ThreadPoolExecutor() as executor:
                scraped_results = list(executor.map(lambda elem: scrape_element(session, elem), elements))
    
        return scraped_results, len(elements)
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return [], 0

def insert_data_into_db(connection, scraped_results):
    cursor = connection.cursor()
    added_count = 0
    
    for res in scraped_results:
        if not product_exists(connection, res["link"]):
            cursor.execute('''
                INSERT INTO products (title, price, link, description)
                VALUES (?, ?, ?, ?)
            ''', (res["title"], res["price"], res["link"], res["description"]))
            logging.info(f"Inserted product: {res['title']}")
            added_count += 1
        else:
            logging.info(f"Product already exists: {res['title']}")
    
    return added_count


def clear_database(connection):
    cursor = connection.cursor()
    cursor.execute("DELETE FROM products")
    connection.commit()
    logging.info("Cleared all items from the database.")

def search_database_by_title(connection, query_param):
    cursor = connection.cursor()
    query = '''SELECT title, price, link, description FROM products WHERE title LIKE ?'''
    cursor.execute(query, ('%{}%'.format(query_param),))
    return cursor.fetchall()

def search_database_by_price(connection, query_param, sort_order='ASC'):
    cursor = connection.cursor()
    operator = "="  # default operator

    # Identify operator in query_param
    if query_param.startswith('<'):
        operator = "<"
        value = query_param[1:].strip()
    elif query_param.startswith('>'):
        operator = ">"
        value = query_param[1:].strip()
    elif query_param.startswith('<='):
        operator = "<="
        value = query_param[2:].strip()
    elif query_param.startswith('>='):
        operator = ">="
        value = query_param[2:].strip()
    else:
        value = query_param.strip()

    try:
        # Convert value to float to ensure it's a number
        float(value)
    except ValueError:
        print("Invalid price input. Please enter a valid number.")
        return []

    # Normalize price in the database by stripping 'kr' and any whitespace
    query = f'''
        SELECT title, price, link, description FROM products 
        WHERE CAST(price AS REAL) {operator} ?
        ORDER BY CAST(price AS REAL) {sort_order}
    '''
    
    logging.info(f"Executing query: {query} with value: {value}")
    cursor.execute(query, (value,))
    return cursor.fetchall()


def log_all_prices(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT id, price FROM products")
    rows = cursor.fetchall()
    for row in rows:
        logging.info(f"ID: {row[0]}, Price: '{row[1]}'")



def set_up_db(connection):
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            title TEXT,
            price TEXT,
            link TEXT,
            description TEXT
        )
    ''')

def count_items_in_database(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM products")
    return cursor.fetchone()[0]

def log_all_entries(connection):
    cursor = connection.cursor()
    cursor.execute("SELECT id, title, link FROM products")
    rows = cursor.fetchall()
    for row in rows:
        logging.info(f"ID: {row[0]}, Title: '{row[1]}', Link: '{row[2]}'")

def main():
    with sqlite3.connect("scraped_data.db") as connection:
        set_up_db(connection)

        # Clean existing database prices
        clean_database_prices(connection)

        # Remove duplicates before scraping new data
        duplicates_removed = remove_duplicates(connection)
        logging.info(f"Number of duplicate items removed: {duplicates_removed}")
        
        initial_count = count_items_in_database(connection)
        logging.info(f"Initial number of items in database: {initial_count}")

        scraped_results, elements_count = scrape_data()
        added_count = insert_data_into_db(connection, scraped_results)
        
        final_count = count_items_in_database(connection)
        
        logging.info(f"Number of elements scraped: {elements_count}")
        logging.info(f"Number of items added: {added_count}")
        logging.info(f"Total number of items in the database: {final_count}")

        # Continuous loop for user input until they choose to exit
        while True:
            search_type = input("Enter search type (title/price) or type 'exit' to quit, 'export' to export or type 'clear' to clear the database or type 'scrape' to scrape: ").strip().lower()
            if search_type == 'exit':
                print("Exiting the program.")
                break

            if search_type not in ['title', 'price', 'clear', 'scrape', 'export']:
                print("Invalid search type. Please enter 'title' or 'price', 'clear', 'scrape' or 'export'.")
                continue
            if search_type == 'clear':
                clear_database(connection)
                new_count = count_items_in_database(connection)
                logging.info(f"Total number of items in the database: {new_count}")
                continue
            if search_type == 'export':
               file_format = input("Enter file format (csv/): ").strip().lower()
            if file_format == 'csv':
               filename = input("Enter the filename (with .csv extension) to export the data to: ").strip() or 'scraped_data.csv'
               export_data_to_csv(connection, filename)
            # elif file_format == 'google sheets':
            #    sheet_name = input("Enter the Google Sheets name to export the data to: ").strip()
            #    share_email = input("Enter your personal Google Account email to share the sheet (optional): ").strip()
            #    export_data_to_google_sheets(connection, sheet_name, share_email=share_email)
            else:
               print("Invalid file format. Please enter 'csv', 'excel', or 'google sheets'.")
               continue

            
            
            if search_type == 'scrape':
                # Clean existing database prices
                clean_database_prices(connection)

                # Remove duplicates before scraping new data
                duplicates_removed = remove_duplicates(connection)
                logging.info(f"Number of duplicate items removed: {duplicates_removed}")
                
                initial_count = count_items_in_database(connection)
                logging.info(f"Initial number of items in database: {initial_count}")

                scraped_results, elements_count = scrape_data()
                added_count = insert_data_into_db(connection, scraped_results)
                
                final_count = count_items_in_database(connection)
                
                logging.info(f"Number of elements scraped: {elements_count}")
                logging.info(f"Number of items added: {added_count}")
                logging.info(f"Total number of items in the database: {final_count}")
                continue
            query_param = input("Enter the product title or price to search for: ").strip()

            if search_type == 'title':
                search_results = search_database_by_title(connection, query_param)
            elif search_type == 'price':
                sort_order = input("Enter sort order (asc/desc): ").strip().lower()
                if sort_order not in ['asc', 'desc']:
                    print("Invalid sort order. Please enter 'asc' or 'desc'.")
                    continue
                search_results = search_database_by_price(connection, query_param, sort_order.upper())

            if search_results:
                for result in search_results:
                    title, price, link, description = result
                    print(f"Title: {title}")
                    print(f"Price: {price}")
                    print(f"Link: {link}")
                    print(f"Description: {description}\n")
            else:
                print("No results found.")
if __name__ == "__main__":
    main()
