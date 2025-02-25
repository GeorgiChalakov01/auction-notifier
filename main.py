# email imports
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# scraping imports
import requests
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime




# email variables
email_subject = f"BCPEA Summary {datetime.today().strftime('%Y-%m-%d')}"

sender_email = 'bcpea.agent@gmail.com'
sender_password = 'qalzizfsqekwyidj'

subscribed_recipient_emails = [
    'gchalakovmmi@gmail.com',
    'hchalakov@abv.bg',
    'milenadqq@abv.bg'
]


# scraping variables
watched_settlements = [
    'гр. Пловдив',
    'с. Браниполе',
    'с. Белащица',
    'с. Марково',
    'с. Първенец',
    'с. Брестовица',
    'с. Скутаре',
    'с. Войводиново',
    'с. Оризари'
]

excluded_property_types = [
    'Офис',
    'Производствен имот',
    'Търговски имот',
]

blacklist_listing_description = [
    'идеални части',
    'идеална част',
    'ид.ч.',
    'ид.част'
]

bcpea_url = "https://sales.bcpea.org/properties?court=16&perpage=9999"



# start scraping
response = requests.get(bcpea_url)
if response.status_code != 200:
    print("Failed to retrieve the webpage.")
    print("Status code:", response.status_code)
    exit()

soup = BeautifulSoup(response.content, "html.parser")

# get all property listing divs
listings = soup.find_all("div", class_="item__group")

# create the variable to hold the email contents
email_content = """
<html>
    <body>
"""


# go through them and construct the email contents
for listing in listings:
    property_type = listing.find("div", "title").text.strip()
    settlement = listing.find_all("div", "info")[0].text.strip()
    address = listing.find_all("div", "info")[1].text.strip()
    area = listing.find("div", "category").text.strip()
    price = listing.find("div", "price").text.strip()
    picture = listing.find("img")['src']
    link = 'https://sales.bcpea.org' + listing.find("a")['href']
    listing_number = listing.find("a")['href'].split('/')[2]
    identifyer = ''

    if settlement:
        if settlement in watched_settlements:
            if (property_type in excluded_property_types) == False:
                current_listing_response = requests.get(link)
                cl_soup = BeautifulSoup(current_listing_response.content, "html.parser")
                current_listing_divs_info = cl_soup.find("div", class_="label__group label__group-description")
                current_listing_description_elements = current_listing_divs_info.find_all("p")
                p_contents = ''
                for p in current_listing_description_elements:
                    p_contents += p.text.strip()
                try:
                    dirty_identifyer = p_contents.split("идентификатор")[1][:30]
                    for letter in dirty_identifyer:
                        if letter in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.']:
                            identifyer += letter
                except:
                    pass
                if any(blacklisted_word in p_contents for blacklisted_word in blacklist_listing_description) == False:
                    current_listing_info = f"""
    <div style='
        background-color: #333; /* Dark grey background */
        padding: 20px;
        border: 1px solid #444; /* Dark grey border */
        border-radius: 10px;
        color: white;
    '>
        <p style='margin-bottom: 10px; color: white;'>Property Type: {property_type}</p>

        <p style='margin-bottom: 10px; color: white;'>Settlement: {settlement}</p>
        
        <p style='margin-bottom: 10px; color: white;'>Address: <a style='text-decoration: none;' href='https://www.google.com/maps/search/{urllib.parse.quote(address)}'>{address}</a></p>
        
        <p style='margin-bottom: 10px; color: white;'>Area: {area}</p>

        <p style='margin-bottom: 10px; color: white;'>Price: {price}</p>

        <p style='margin-bottom: 10px; color: white;'>KaisCadastre ID: {identifyer}</p>

        <a style='text-decoration: none;' href='https://kais.cadastre.bg/bg/Map'>KaisCadastre</a>
        
        <p style='margin-bottom: 10px;'>
            <a href='{link}'>
                <img style='width: 100%; height: auto' src='https://sales.bcpea.org{picture}'/>
            </a>
        </p>
    </div>
    <br/>
"""
                    email_content += current_listing_info

email_content += """
    </body>
</html>
"""



# send the email
for recipient_email in subscribed_recipient_emails:
    msg = MIMEMultipart()
    msg['Subject'] = email_subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    html_part = MIMEText(email_content, 'html')
    msg.attach(html_part)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, sender_password)

    server.sendmail(sender_email, recipient_email, msg.as_string())
    server.quit()
