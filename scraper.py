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
            key = (row['court'], row['id'])
            if key not in filters:
                filters[key] = {
                    'settlements': [s.strip() for s in row['settlements'].split(',')] if row['settlements'] else [],
                    'excluded': [e.strip() for e in row['excluded_property_types'].split(',')] if row['excluded_property_types'] else [],
                    'blacklist': [b.strip().lower() for b in row['blacklist'].split(',')] if row['blacklist'] else [],
                    'users': set()
                }
            filters[key]['users'].add(row['email'])
        
        conn.close()
        logging.info(f"Loaded {len(filters)} active filter groups")
        return filters
    except Exception as e:
        logging.error(f"Error loading filters: {str(e)}")
        return {}

def scrape_and_notify():
    """Main scraping function"""
    logging.info("🚀 Starting scraping process")
    filters = get_active_filters()
    
    if not filters:
        logging.warning("⚠️ No active filters found")
        return

    user_listings = {}
    total_processed = 0

    for (court, fg_id), fg in filters.items():
        logging.info(f"🔍 Processing court {court} (Filter Group {fg_id})")
        url = f"https://sales.bcpea.org/properties?court={court}&perpage=9999"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            logging.info(f"🌐 Successfully fetched {url}")
        except Exception as e:
            logging.error(f"❌ Failed to fetch {url}: {str(e)}")
            continue

        soup = BeautifulSoup(response.content, 'html.parser')
        listings = soup.find_all("div", class_="item__group")
        logging.info(f"🏠 Found {len(listings)} listings for court {court}")

        fg_listings = []
        for idx, listing in enumerate(listings):
            try:
                # Extract basic info
                prop_type = listing.find("div", class_="title").text.strip()
                settlement = listing.find_all("div", class_="info")[0].text.strip()
                address = listing.find_all("div", class_="info")[1].text.strip()
                area = listing.find("div", class_="category").text.strip()
                price = listing.find("div", class_="price").text.strip()
                link = 'https://sales.bcpea.org' + listing.find("a")['href']
                img = listing.find("img")['src']
                listing_number = link.split('/')[-1]

                logging.info(f"📄 Processing listing {idx+1}/{len(listings)}: {prop_type} in {settlement}")

                # Fetch details page
                try:
                    details_page = requests.get(link, timeout=5)
                    details_page.raise_for_status()
                except Exception as e:
                    logging.warning(f"⚠️ Failed to fetch details page {link}: {str(e)}")
                    continue

                # Extract description and Kais ID
                details_soup = BeautifulSoup(details_page.content, 'html.parser')
                description_div = details_soup.find("div", class_="label__group label__group-description")
                description = ' '.join([p.text.strip() for p in description_div.find_all("p")]) if description_div else ""
                
                # Blacklist check
                if any(term in description.lower() for term in fg['blacklist']):
                    logging.info(f"⛔ Skipping listing {link} due to blacklist match")
                    continue

                # Settlement filter
                if fg['settlements'] and settlement not in fg['settlements']:
                    logging.info(f"⛔ Skipping listing {link} - settlement mismatch")
                    continue

                # Property type filter
                if prop_type in fg['excluded']:
                    logging.info(f"⛔ Skipping listing {link} - excluded type")
                    continue

                # Extract KaisCadastre ID
                kais_id = "Not found"
                if description:
                    try:
                        id_part = description.split("идентификатор")[1][:30]
                        kais_id = ''.join([c for c in id_part if c in '0123456789.'])
                        logging.info(f"🔑 Found KaisCadastre ID: {kais_id}")
                    except Exception as e:
                        logging.warning(f"⚠️ Could not extract KaisCadastre ID: {str(e)}")

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
                                    <li><i class="bi bi-building"></i> Type: {prop_type}</li>
                                    <li><i class="bi bi-geo-alt"></i> Location: {settlement}</li>
                                    <li><i class="bi bi-pin-map"></i> Address: 
                                        <a href="https://maps.google.com/?q={urllib.parse.quote(address)}" target="_blank">
                                            {address}
                                        </a>
                                    </li>
                                    <li><i class="bi bi-arrows-fullscreen"></i> Area: {area}</li>
                                    <li><i class="bi bi-tag"></i> Price: {price}</li>
                                    <li><i class="bi bi-fingerprint"></i> KaisCadastre ID: {kais_id}</li>
                                </ul>
                                <div class="mt-2">
                                    <a href="https://kais.cadastre.bg/bg/Map" class="btn btn-primary btn-sm" style="color: white;" target="_blank">
                                        <i class="bi bi-map"></i> Open KaisCadastre
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                '''
                fg_listings.append(listing_html)
                total_processed += 1

            except Exception as e:
                logging.error(f"❌ Error processing listing: {str(e)}")

        # Add filter group listings to users
        court_name = next((name for num, name in COURT_CHOICES if num == int(court)), 'Unknown Court')
        for user in fg['users']:
            if user not in user_listings:
                user_listings[user] = {}
            user_listings[user][fg_id] = {
                'court': court_name,
                'count': len(fg_listings),
                'listings': fg_listings
            }

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
                        <h3>{data['court']} (Filter Group {fg_id})</h3>
                        <p class="count-badge">{data['count']} properties found</p>
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
                        Property Listings Summary
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
