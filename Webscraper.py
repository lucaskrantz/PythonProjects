import requests
from bs4 import BeautifulSoup

URL = "https://jus.se/collections/all-menswear/men"
page = requests.get(URL)

soup = BeautifulSoup(page.content, "html.parser")
results = soup.find(id="PageContainer")
#print(results.prettify()) 

#job_locations = results.find_all(class_="location")
#for job_location in job_locations:
#    print(job_location.text.strip(), end="\n"*2)
elements = results.find_all("div", class_="grid-view-item product-card")
for element in elements:
    title_element = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    price_element = element.find("span", class_="price-item price-item--regular")
    links = element.find("a", class_="grid-view-item__link grid-view-item__image-container full-width-link")
    link_url = links["href"]
    print(title_element.text.strip())
    print(price_element.text.strip())
    print(f"Link: https://jus.se{link_url}\n")
    
print(len(elements))
    