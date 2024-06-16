import concurrent.futures
import requests
from bs4 import BeautifulSoup
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to get product data
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

# Function to scrape element data
def scrape_element(session, element):
    title_element = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    price_element = element.find("span", class_="price-item price-item--regular")
    link_url = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")["href"]

    prod_desc = get_product_data(session, f"https://jus.se{link_url}")
    
    return {
        "title": title_element.text.strip(),
        "price": price_element.text.strip(),
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

    for res in scraped_results:
        cursor.execute('''
            INSERT INTO products (title, price, link, description)
            VALUES (?, ?, ?, ?)
        ''', (res["title"], res["price"], res["link"], res["description"]))

        logging.info(f"Inserted product: {res['title']}")

def search_database(connection, query_param):
    cursor = connection.cursor()
    query = '''SELECT title, price, link, description FROM products WHERE title LIKE ?'''
    cursor.execute(query, ('%{}%'.format(query_param),))
    return cursor.fetchall()

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

def main():
    with sqlite3.connect("scraped_data.db") as connection:
        set_up_db(connection)

        initial_count = count_items_in_database(connection)
        logging.info(f"Initial number of items in database: {initial_count}")

        scraped_results, elements_count = scrape_data()
        insert_data_into_db(connection, scraped_results)
        
        final_count = count_items_in_database(connection)
        added_count = final_count - initial_count
        
        logging.info(f"Number of elements scraped: {elements_count}")
        logging.info(f"Number of items added: {added_count}")
        logging.info(f"Total number of items in the database: {final_count}")

        user_input = input("Enter a product title to search for: ")
        search_results = search_database(connection, user_input)

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