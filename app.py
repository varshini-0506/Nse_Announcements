from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import time
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_driver():
    """Create and configure Chrome WebDriver with headless options and performance optimizations"""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    # Performance optimizations
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--disable-ipc-flooding-protection')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # Disable images to speed up loading
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # Block images
        "profile.default_content_setting_values.notifications": 2
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    try:
        # Try to use system ChromeDriver first, fallback to webdriver-manager
        if os.path.exists('/usr/local/bin/chromedriver'):
            service = Service('/usr/local/bin/chromedriver')
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            # Fallback to webdriver-manager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"Error creating driver: {str(e)}")
        # Last resort: try without explicit service
        try:
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e2:
            logger.error(f"Error creating driver (fallback): {str(e2)}")
            raise


def scrape_announcements(symbol):
    """
    Scrape NSE announcements for a given symbol using optimized JavaScript extraction
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE')
    
    Returns:
        list: List of announcement dictionaries
    """
    driver = None
    try:
        driver = create_driver()
        url = f"https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={symbol.upper()}"
        
        logger.info(f"Navigating to URL: {url}")
        driver.get(url)
        
        # Wait for the table to be present and rows to be loaded
        logger.info("Waiting for table to load...")
        wait = WebDriverWait(driver, 30)
        
        # Wait for table rows to be loaded (more efficient than waiting for table first)
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#CFanncEquityTable tbody tr"))
        )
        
        # Wait for table to be stable (no new rows being added)
        # Check row count stability instead of fixed sleep
        previous_count = 0
        stable_count = 0
        for _ in range(10):  # Check up to 10 times (max 1 second)
            current_rows = driver.find_elements(By.CSS_SELECTOR, "#CFanncEquityTable tbody tr")
            current_count = len(current_rows)
            if current_count == previous_count and current_count > 0:
                stable_count += 1
                if stable_count >= 2:  # Stable for 2 checks
                    break
            else:
                stable_count = 0
            previous_count = current_count
            time.sleep(0.1)  # Small delay between checks
        
        logger.info(f"Found {previous_count} announcement rows")
        
        # Use JavaScript to extract all data at once (much faster than DOM queries)
        logger.info("Extracting data using JavaScript...")
        announcements = driver.execute_script("""
            var rows = document.querySelectorAll('#CFanncEquityTable tbody tr');
            var results = [];
            
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll('td');
                if (cells.length < 7) continue;
                
                var announcement = {};
                
                // Symbol
                var symbolCell = cells[0];
                announcement.symbol = symbolCell.textContent.trim();
                var symbolLink = symbolCell.querySelector('a');
                announcement.symbol_link = symbolLink ? symbolLink.href : '';
                
                // Company Name
                announcement.company_name = cells[1].textContent.trim();
                
                // Subject
                announcement.subject = cells[2].textContent.trim();
                
                // Details
                var detailsCell = cells[3];
                var readMoreSpan = detailsCell.querySelector('span.content.eclipse');
                announcement.details = readMoreSpan ? readMoreSpan.textContent.trim() : detailsCell.textContent.trim();
                
                // Attachment
                var attachmentCell = cells[4];
                var attachmentLink = attachmentCell.querySelector('a');
                announcement.attachment_url = attachmentLink ? attachmentLink.href : '';
                var sizeElem = attachmentCell.querySelector('p');
                announcement.attachment_size = sizeElem ? sizeElem.textContent.trim() : '';
                
                // XBRL
                var xbrlCell = cells[5];
                var xbrlLink = xbrlCell.querySelector('a');
                announcement.xbrl_url = xbrlLink ? xbrlLink.href : '';
                
                // Broadcast Date/Time
                var dateCell = cells[6];
                var dateLink = dateCell.querySelector('a');
                announcement.broadcast_date = dateLink ? dateLink.textContent.trim() : dateCell.textContent.trim();
                
                results.push(announcement);
            }
            
            return results;
        """)
        
        logger.info(f"Successfully scraped {len(announcements)} announcements")
        return announcements
        
    except TimeoutException:
        logger.error("Timeout waiting for table to load")
        raise Exception("Timeout: Table did not load within the expected time")
    except WebDriverException as e:
        logger.error(f"WebDriver error: {str(e)}")
        raise Exception(f"WebDriver error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise Exception(f"Error scraping announcements: {str(e)}")
    finally:
        if driver:
            driver.quit()
            logger.info("Driver closed")


@app.route('/announcements', methods=['GET'])
def get_announcements():
    """
    Endpoint to get announcements for a given symbol
    
    Query Parameters:
        symbol: Stock symbol (required)
    
    Returns:
        JSON response with announcements or error message
    """
    symbol = request.args.get('symbol')
    
    if not symbol:
        return jsonify({
            "error": "Symbol parameter is required",
            "example": "/announcements?symbol=RELIANCE"
        }), 400
    
    try:
        announcements = scrape_announcements(symbol)
        return jsonify({
            "symbol": symbol.upper(),
            "count": len(announcements),
            "announcements": announcements
        }), 200
    except Exception as e:
        logger.error(f"Error in get_announcements: {str(e)}")
        return jsonify({
            "error": str(e),
            "symbol": symbol.upper()
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API information"""
    return jsonify({
        "message": "NSE Announcements Scraper API",
        "endpoints": {
            "/announcements": "GET - Get announcements for a symbol. Query param: symbol (required)",
            "/health": "GET - Health check endpoint"
        },
        "example": "/announcements?symbol=RELIANCE"
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

