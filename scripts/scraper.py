import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def capture_looker():
    url = os.environ.get("LOOKER_REPORT_URL")
    if not url: return False

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")
    
    # Cloud/Server compatibility settings
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get(url)
        time.sleep(15) # Wait for Looker to load
        driver.save_screenshot("report.png")
        driver.quit()
        return True
    except Exception as e:
        print(f"Scraper Error: {e}")
        return False