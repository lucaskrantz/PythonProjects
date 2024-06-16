import concurrent.futures
import requests
from bs4 import BeautifulSoup
import sqlite3


connection = sqlite3.connect("scraped_data.db")


# Function to get product data
def get_product_data(url):
    print(f"Running {url}")
    product_page = requests.get(url)
    product_soup = BeautifulSoup(product_page.content, "html.parser")
    desc_tag = product_soup.find('div', class_='product-single__description rte')
    if desc_tag:
        desc_text = desc_tag.text.strip()
    else:
        desc_text = None
    return desc_text

# Function to scrape element data
def scrape_element(element):
    title_element = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    price_element = element.find("span", class_="price-item price-item--regular")
    links = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    link_url = links["href"]

    prod_desc = get_product_data(f"https://jus.se{link_url}")
    
    return {
        "title": title_element.text.strip(),
        "price": price_element.text.strip(),
        "link": f"https://jus.se{link_url}",
        "description": prod_desc
    }


def scrape_data():
    URL = "https://jus.se/collections/all-menswear/men"
    page = requests.get(URL)
    soup = BeautifulSoup(page.content, "html.parser")
    results = soup.find(id="PageContainer")
    elements = results.find_all("div", class_="grid-view-item product-card")

    # Use the ThreadPoolExecutor to scrape the elements concurrently
    with concurrent.futures.ThreadPoolExecutor() as executor:
        scraped_results = list(executor.map(scrape_element, elements))

    # Return the scraped results and the number of elements
    return scraped_results, len(elements)



def insert_data_into_db(scraped_results):

    cursor = connection.cursor()
    # Insert the scraped data into the database
    for res in scraped_results:
        cursor.execute('''
        INSERT INTO products (title, price, link, description)
        VALUES (?, ?, ?, ?)
    ''', (res["title"], res["price"], res["link"], res["description"]))

    # Print the scraped results for transparency
    print(res["title"])
    print(res["price"])
    print(f"Link: {res['link']}")
    print(res["description"])
    print()

    # Commit the changes 
    connection.commit()


def search_database(query_param):
    # Connect to the SQLite database
    connection = sqlite3.connect("scraped_data.db")
    cursor = connection.cursor()

    # Formulate the query using parameterized SQL to avoid SQL injection
    query = '''SELECT title, price, link, description FROM products WHERE title LIKE ?'''
    
    # Execute the query with the user input
    cursor.execute(query, ('%' + query_param + '%',))

    # Fetch all results
    results = cursor.fetchall()

    # Close the database connection
    connection.close()

    return results


def set_up_db():
    # Set up the database connection and cursor
    cursor = connection.cursor()
    
    # Create the products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            title TEXT,
            price TEXT,
            link TEXT,
            description TEXT
        )
    ''')    
    


def main():
    
    
    set_up_db()
    
    # Perform data scraping and database insertion
    scraped_results, elements_count = scrape_data()
    insert_data_into_db(scraped_results)
    
    # Print the number of elements scraped
    print(f"Number of elements scraped: {elements_count}")

    # Get user input for searching the database
    user_input = input("Enter a product title to search for: ")
    search_results = search_database(user_input)

    # Display the search results
    if search_results:
        for result in search_results:
            title, price, link, description = result
            print(f"Title: {title}")
            print(f"Price: {price}")
            print(f"Link: {link}")
            print(f"Description: {description}\n")
    else:
        print("No results found.")
        
    connection.close()


if __name__ == "__main__":
    main()
