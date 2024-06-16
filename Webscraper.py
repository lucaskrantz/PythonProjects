import concurrent.futures
import requests
from bs4 import BeautifulSoup

URL = "https://jus.se/collections/all-menswear/men"
page = requests.get(URL)

soup = BeautifulSoup(page.content, "html.parser")
results = soup.find(id="PageContainer")
elements = results.find_all("div", class_="grid-view-item product-card")

def get_product_data(url):
    """This method will fetch data for a single product."""
    print(f"Running {url}")
    product_page = requests.get(url)
    product_soup = BeautifulSoup(product_page.content, "html.parser")
    desc_tag = product_soup.find('div', class_='product-single__description rte')
    if desc_tag:
        desc_text = desc_tag.text.strip()
    else:
        desc_text = None
    
    return desc_text

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

with concurrent.futures.ThreadPoolExecutor() as executor:
    results = list(executor.map(scrape_element, elements))

for res in results:
    print(res["title"])
    print(res["price"])
    print(f"Link: {res['link']}")
    print(res["description"])
    print()
    
print(len(elements))