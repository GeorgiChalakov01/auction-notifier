# scraper.py
import sqlite3
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scraper.log')
    ]
)

# Email configuration
sender_email = 'bcpea.agent@gmail.com'
sender_password = 'qalzizfsqekwyidj'

COURT_CHOICES = [
    (1, 'Благоевград'), (2, 'Бургас'), (3, 'Варна'), (4, 'Велико Търново'),
    (5, 'Видин'), (6, 'Враца'), (7, 'Габрово'), (8, 'Добрич'), (9, 'Кърджали'),
    (10, 'Кюстендил'), (11, 'Ловеч'), (12, 'Монтана'), (13, 'Пазарджик'),
    (14, 'Перник'), (15, 'Плевен'), (16, 'Пловдив'), (17, 'Разград'),
    (18, 'Русе'), (19, 'Силистра'), (20, 'Сливен'), (21, 'Смолян'),
    (22, 'София град'), (23, 'София окръг'), (24, 'Стара Загора'),
    (25, 'Търговище'), (26, 'Хасково'), (27, 'Шумен'), (28, 'Ямбол')
]

def get_active_filters():
    """Retrieve active filters from database"""
    try:
        conn = sqlite3.connect('instance/bcpea.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fg.*, u.email 
            FROM filter_groups fg
            JOIN user_filters uf ON fg.id = uf.filter_group_id
            JOIN users u ON uf.user_id = u.id
        ''')
        
        filters = {}
        for row in cursor:
            key = (row['type'], row['court'], row['id'])
            if key not in filters:
                filters[key] = {
                    'settlements': [s.strip() for s in row['settlements'].split(',')] if row['settlements'] else [],
                    'excluded': [e.strip() for e in row['excluded_property_types'].split(',')] if row['excluded_property_types'] else [],
                    'blacklist': [b.strip().lower() for b in row['blacklist'].split(',')] if row['blacklist'] else [],
                    'required_title_words': [t.strip().lower() for t in row['required_title_words'].split(',')] 
                        if row['required_title_words'] else [],
                    'required_description_words': [d.strip().lower() for d in row['required_description_words'].split(',')] 
                        if row['required_description_words'] else [],
                    'users': set()
                }
            filters[key]['users'].add(row['email'])
        
        conn.close()
        return filters
    except Exception as e:
        logging.error(f"Error loading filters: {str(e)}")
        return {}

def process_listing(title, description, fg):
    """Validate listing against required words"""
    try:
        # Check required title words
        if fg.get('required_title_words'):
            title_lower = title.lower()
            if not all(word in title_lower 
                      for word in fg['required_title_words']):
                return False

        # Check required description words
        if fg.get('required_description_words'):
            desc_lower = description.lower()
            if not all(word in desc_lower 
                      for word in fg['required_description_words']):
                return False
        
        return True
    except Exception as e:
        logging.error(f"Filter validation error: {str(e)}")
        return False

def scrape_vehicles(court, fg_id, fg):
    """Scrape vehicle listings with pagination and filtering"""
    base_url = f"https://sales.bcpea.org/vehicles?court={court}"
    page = 1
    all_listings = []
    
    while True:
        try:
            url = f"{base_url}&p={page}"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Check for no results
            if soup.find('p', string='Няма намерени резултати'):
                break

            listings = soup.find_all("div", class_="item__group")
            logging.info(f"🚗 Found {len(listings)} vehicles on page {page}")

            for listing in listings:
                try:
                    # Extract basic info
                    header = listing.find("div", class_="header")
                    title = header.find("div", class_="title").text.strip()
                    category = header.find("div", class_="category").text.strip()
                    
                    # Extract settlement
                    settlement_div = listing.find("div", class_="label__group", 
                                                string=lambda t: "НАСЕЛЕНО МЯСТО" in t if t else False)
                    settlement = (settlement_div.find_next("div", class_="info").text.strip() 
                            if settlement_div else "Unknown")
                    
                    # Extract price
                    price_div = listing.find("div", class_="content--price")
                    price = (price_div.find("div", class_="price").text.strip() 
                            if price_div else "N/A")
                    
                    link = 'https://sales.bcpea.org' + listing.find("a")['href']
                    img = listing.find("img")['src']

                    # Fetch description
                    try:
                        details_response = requests.get(link, timeout=10)
                        details_soup = BeautifulSoup(details_response.content, 'html.parser')
                        description_div = details_soup.find("div", class_="label__group-description")
                        description = (' '.join([p.text.strip() for p in description_div.find_all("p")]) 
                                    if description_div else "")
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to fetch vehicle details: {str(e)}")
                        continue

                    # Convert to lowercase for filtering
                    title_lower = title.lower()
                    description_lower = description.lower()
                    settlement_lower = settlement.lower()
                    category_lower = category.lower()

                    # Apply filters
                    filter_reasons = []
                    
                    # Required title words
                    if fg['required_title_words']:
                        missing_words = [word for word in fg['required_title_words'] 
                                       if word not in title_lower]
                        if missing_words:
                            filter_reasons.append(f"missing title words: {', '.join(missing_words)}")

                    # Required description words
                    if fg['required_description_words']:
                        missing_words = [word for word in fg['required_description_words'] 
                                       if word not in description_lower]
                        if missing_words:
                            filter_reasons.append(f"missing description words: {', '.join(missing_words)}")

                    # Settlement filter
                    if fg['settlements'] and settlement_lower not in [s.lower() for s in fg['settlements']]:
                        filter_reasons.append("settlement mismatch")

                    # Category filter
                    if category_lower in [e.lower() for e in fg['excluded']]:
                        filter_reasons.append("excluded category")

                    # Blacklist filter
                    if any(term in description_lower for term in fg['blacklist']):
                        filter_reasons.append("blacklisted term")

                    if filter_reasons:
                        logging.info(f"⛔ Skipping vehicle {link} - {', '.join(filter_reasons)}")
                        continue

                    # Build listing HTML
                    listing_html = f'''
                    <div class="listing-card mb-3">
                        <div class="row g-0">
                            <div class="col-md-4">
                                <a href="{link}" target="_blank">
                                    <img src="https://sales.bcpea.org{img}" class="listing-image">
                                </a>
                            </div>
                            <div class="col-md-8">
                                <div class="listing-body">
                                    <ul class="list-unstyled">
                                        <li><i class="bi bi-car-front"></i> {title}</li>
                                        <li><i class="bi bi-tag"></i> Category: {category}</li>
                                        <li><i class="bi bi-geo-alt"></i> Location: {settlement}</li>
                                        <li><i class="bi bi-cash"></i> Price: {price}</li>
                                        <li class="text-muted small">Filter Group: {fg_id}</li>
                                    </ul>
                                    <div class="mt-2">
                                        <a href="{link}" class="btn btn-primary btn-sm" target="_blank" style="color: white;">
                                            <i class="bi bi-eye"></i> View Details
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    '''
                    all_listings.append(listing_html)

                except Exception as e:
                    logging.error(f"❌ Vehicle processing error: {str(e)}")

            page += 1

        except Exception as e:
            logging.error(f"❌ Vehicle page error: {str(e)}")
            break

    return all_listings

def scrape_properties(court, fg_id, fg):
    """Scrape property listings with full filtering"""
    url = f"https://sales.bcpea.org/properties?court={court}&perpage=9999"
    listings = []
    
    try:
        response = requests.get(url, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        property_listings = soup.find_all("div", class_="item__group")
        logging.info(f"🏠 Found {len(property_listings)} properties")

        for listing in property_listings:
            try:
                # Extract basic info
                prop_type = listing.find("div", class_="title").text.strip()
                info_divs = listing.find_all("div", class_="info")
                settlement = info_divs[0].text.strip() if len(info_divs) > 0 else "Unknown"
                address = info_divs[1].text.strip() if len(info_divs) > 1 else "N/A"
                area = listing.find("div", class_="category").text.strip()
                price = listing.find("div", class_="price").text.strip()
                link = 'https://sales.bcpea.org' + listing.find("a")['href']
                img = listing.find("img")['src']

                # Fetch description
                try:
                    details_response = requests.get(link, timeout=10)
                    details_soup = BeautifulSoup(details_response.content, 'html.parser')
                    description_div = details_soup.find("div", class_="label__group-description")
                    description = (' '.join([p.text.strip() for p in description_div.find_all("p")]) 
                                if description_div else "")
                except Exception as e:
                    logging.warning(f"⚠️ Failed to fetch property details: {str(e)}")
                    continue

                # Convert to lowercase for filtering
                title_lower = prop_type.lower()
                description_lower = description.lower()
                settlement_lower = settlement.lower()

                # Apply filters
                filter_reasons = []
                
                # Required title words
                if fg['required_title_words']:
                    missing_words = [word for word in fg['required_title_words'] 
                                   if word not in title_lower]
                    if missing_words:
                        filter_reasons.append(f"missing title words: {', '.join(missing_words)}")

                # Required description words
                if fg['required_description_words']:
                    missing_words = [word for word in fg['required_description_words'] 
                                   if word not in description_lower]
                    if missing_words:
                        filter_reasons.append(f"missing description words: {', '.join(missing_words)}")

                # Settlement filter
                if fg['settlements'] and settlement_lower not in [s.lower() for s in fg['settlements']]:
                    filter_reasons.append("settlement mismatch")

                # Property type filter
                if prop_type.lower() in [e.lower() for e in fg['excluded']]:
                    filter_reasons.append("excluded type")

                # Blacklist filter
                if any(term in description_lower for term in fg['blacklist']):
                    filter_reasons.append("blacklisted term")

                if filter_reasons:
                    logging.info(f"⛔ Skipping property {link} - {', '.join(filter_reasons)}")
                    continue

                # Extract KaisCadastre ID
                kais_id = "Not found"
                if description:
                    try:
                        id_part = description.split("идентификатор")[1][:30]
                        kais_id = ''.join([c for c in id_part if c in '0123456789.'])
                    except:
                        pass

                # Build listing HTML
                listing_html = f'''
                <div class="listing-card mb-3">
                    <div class="row g-0">
                        <div class="col-md-4">
                            <a href="{link}" target="_blank">
                                <img src="https://sales.bcpea.org{img}" class="listing-image">
                            </a>
                        </div>
                        <div class="col-md-8">
                            <div class="listing-body">
                                <ul class="list-unstyled">
                                    <li><i class="bi bi-building"></i> {prop_type}</li>
                                    <li><i class="bi bi-geo-alt"></i> {settlement}</li>
                                    <li><i class="bi bi-pin-map"></i> 
                                        <a href="https://maps.google.com/?q={urllib.parse.quote(address)}" 
                                           target="_blank">{address}</a>
                                    </li>
                                    <li><i class="bi bi-arrows-fullscreen"></i> {area}</li>
                                    <li><i class="bi bi-tag"></i> {price}</li>
                                    <li><i class="bi bi-fingerprint"></i> KAIS ID: {kais_id}</li>
                                    <li class="text-muted small">Filter Group: {fg_id}</li>
                                </ul>
                                <div class="mt-2">
                                    <a href="https://kais.cadastre.bg/bg/Map" 
                                       class="btn btn-primary btn-sm" 
                                       target="_blank">
                                        <i class="bi bi-map"></i> KaisCadastre
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                '''
                listings.append(listing_html)

            except Exception as e:
                logging.error(f"❌ Property processing error: {str(e)}")

    except Exception as e:
        logging.error(f"❌ Property page error: {str(e)}")

    return listings

def scrape_and_notify():
    """Main scraping function"""
    logging.info("🚀 Starting scraping process")
    filters = get_active_filters()
    
    if not filters:
        logging.warning("⚠️ No active filters found")
        return

    user_listings = {}
    total_processed = 0

    for (filter_type, court, fg_id), fg in filters.items():
        logging.info(f"🔍 Processing {filter_type} court {court} (Filter Group {fg_id})")
        
        if filter_type == 'property':
            listings = scrape_properties(court, fg_id, fg)
        elif filter_type == 'vehicle':
            listings = scrape_vehicles(court, fg_id, fg)
        else:
            logging.warning(f"⚠️ Unknown filter type: {filter_type}")
            continue

        # Add listings to users
        court_name = next((name for num, name in COURT_CHOICES if num == int(court)), 'Unknown Court')
        for user in fg['users']:
            if user not in user_listings:
                user_listings[user] = {}
            user_listings[user][fg_id] = {
                'type': filter_type.capitalize(),
                'court': court_name,
                'count': len(listings),
                'listings': listings
            }
        total_processed += len(listings)

    logging.info(f"🏁 Scraping complete. Processed {total_processed} listings total")
    send_emails(user_listings)

def send_emails(user_listings):
    """Send emails to users with their filtered listings"""
    if not user_listings:
        logging.warning("No listings to send")
        return

    logging.info(f"📧 Preparing to send emails to {len(user_listings)} users")
    
    for user, fg_data in user_listings.items():
        try:
            msg = MIMEMultipart()
            msg['Subject'] = f"BCPEA Summary {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = sender_email
            msg['To'] = user

            # Build email body
            sections = []
            for fg_id, data in fg_data.items():
                section_html = f'''
                <div class="filter-group">
                    <div class="group-header">
                        <h3>{data['type']} Listings - {data['court']} (Filter Group {fg_id})</h3>
                        <p class="count-badge">{data['count']} items found</p>
                    </div>
                    <div class="listings">
                        {"".join(data['listings'])}
                    </div>
                </div>
                '''
                sections.append(section_html)

            body = f'''
            <html>
                <head>
                    <style>
                        .filter-group {{ 
                            border: 1px solid #ddd; 
                            border-radius: 8px; 
                            margin-bottom: 1.5rem; 
                            padding: 1rem;
                        }}
                        .group-header {{ 
                            border-bottom: 2px solid #eee; 
                            padding-bottom: 0.5rem; 
                            margin-bottom: 1rem;
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                        }}
                        .count-badge {{
                            background: #007bff;
                            color: white;
                            padding: 0.25rem 0.75rem;
                            border-radius: 20px;
                            font-size: 0.9em;
                        }}
                        .listing-card {{
                            background: #f8f9fa;
                            border-radius: 8px;
                            padding: 1rem;
                            margin-bottom: 1rem;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        }}
                        .listing-image {{
                            max-width: 100%;
                            height: auto;
                            border-radius: 4px;
                        }}
                        .list-unstyled li {{
                            margin-bottom: 0.5rem;
                            padding: 0.5rem;
                            background: white;
                            border-radius: 4px;
                            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
                        }}
                        .btn-primary {{
                            background: #007bff;
                            border: none;
                            padding: 0.375rem 0.75rem;
                            border-radius: 4px;
                        }}
                    </style>
                </head>
                <body>
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 0.5rem;">
                        Auction Listings Summary
                    </h2>
                    {"".join(sections)}
                    <footer style="margin-top: 2rem; padding-top: 1rem; color: #7f8c8d; text-align: center;">
                        Generated by BCPEA Notifier • {datetime.now().strftime('%Y-%m-%d %H:%M')}
                    </footer>
                </body>
            </html>
            '''

            msg.attach(MIMEText(body, 'html'))
            
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, user, msg.as_string())
            
            logging.info(f"✉️ Email sent to {user}")
        except Exception as e:
            logging.error(f"❌ Failed to send email to {user}: {str(e)}")

if __name__ == '__main__':
    scrape_and_notify()
