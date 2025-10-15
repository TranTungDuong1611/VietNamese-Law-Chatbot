import os
import time
import json
from urllib.parse import urljoin
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options

class QALawCrawler:
    def __init__(self, headless=True):
        self.HOME_PAGE = "https://thuvienphapluat.vn/hoi-dap-phap-luat/quyen-dan-su"

        # Chrome options
        
        self.chrome_options = webdriver.ChromeOptions()
        if headless:
           self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument("--disable-extensions")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.page_load_strategy = "normal"

        self.driver = None

    def init_driver(self):
        """Initialize Chrome driver"""
        self.driver = webdriver.Chrome(options=self.chrome_options)

    def close_driver(self):
        """Close Chrome driver"""
        if self.driver:
            self.driver.close()
    
    def crawl_query_url(self, num_query_page=100):
        """Crawl query URLs from a page"""
        if not self.driver:
            self.init_driver()
        
        query_url_list = []
        for page in range(1, num_query_page+1):
            try:
                page_url = f"{self.HOME_PAGE}?page={page}"
                print(f"Crawling query page: {page_url}")
                self.driver.get(page_url)

                # Extract query urls in this page
                tags = self.driver.find_elements(By.CSS_SELECTOR, value="article.news-card")

                if not tags:
                    print(f"No query URLs found at {page_url}. Stopping crawl.")
                    continue
                
                for tag in tags: 
                    link_tag = tag.find_element(By.TAG_NAME, "a")
                    href = link_tag.get_attribute("href").strip()
                
                    if not href.startswith(self.HOME_PAGE):
                        continue

                    if href not in query_url_list:
                        query_url_list.append(href)
                             
            except (StaleElementReferenceException, NoSuchElementException):
                continue
            except Exception as e:
                print(f"Error processing query page: {e}")
        return query_url_list
    
    def _clean_text(s: str) -> str:
        """Clean query and context"""
        return " ".join(s.split()).strip()

    def extract_query_and_context(self, url):
        """Extract query and context from URL"""
        if not self.driver:
            self.init_driver()

        try:
            self.driver.get(url)
            wait = WebDriverWait(self.driver, 10)

            # Find main content
            content = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section.news-content")))
            nodes = content.find_elements(By.XPATH, "./*")

            qas = []
            current_q = None
            buf = []

            def flush():
                """Close current QA and save to qas"""
                nonlocal current_q, buf
                if current_q and buf:
                    ctx = "\n".join([self._clean_text(x) for x in buf if self._clean_text(x)]).strip()
                    if ctx:
                        qas.append(
                            {
                                "query": self._clean_text(current_q),
                                "context": ctx,
                            }
                        )
                current_q, buf = None, []

            for el in nodes:
                tag = el.tag_name.lower()

                # Skip inrelevant content
                if tag in {"script", "style", "noscript"}:
                    continue
                if len(el.find_elements(By.TAG_NAME, "em")) > 0:
                    continue

                if tag == "h2":
                    flush()
                    current_q = el.text.strip()
                    continue

                # Get context of current query
                if current_q:
                    if tag in {"p", "blockquote"}:
                        txt = el.text.strip()
                        if txt:
                            buf.append(txt)
                    elif tag in {"ul", "ol"}:
                        items = [
                            li.text.strip()
                            for li in el.find_elements(By.TAG_NAME, "li")
                            if li.text.strip()
                        ]
                        if items:
                            buf.append("\n".join(f"- {t}" for t in items))

            # Save the last QA
            flush()

            print(f"Extracted {len(qas)} QAs from {url}")
            return qas

        except TimeoutException:
            print(f"[TIMEOUT] Cannot load content from {url}")
            return []
        except Exception as e:
            print(f"[ERROR] Failed to extract QAs from {url}: {e}")
            return []

    def crawl_all_queries(self, num_pages=100, output_dir="data/raw_data"):
        """Crawl all Q&A pairs and save to JSON"""
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Collect query URLs
        query_urls = self.crawl_query_url(num_query_page=num_pages)
        print(f"Collected {len(query_urls)} query URLs")

        if not query_urls:
            print("No URLs found. Stopping crawl.")
            return

        # Extract query and context
        all_qas = []
        for i, url in enumerate(query_urls, start=1):
            print(f"[{i}/{len(query_urls)}] Extracting QAs from: {url}")

            try:
                qas = self.extract_query_and_context(url)
                if not qas:
                    print(f" No QAs found in {url}")
                    continue

                for qa in qas:
                    qa["source_url"] = url  # thêm thông tin nguồn để trace ngược
                    all_qas.append(qa)

            except Exception as e:
                print(f"[ERROR] Failed at {url}: {e}")
                continue

        # Save QAs to json file
        output_file = os.path.join(output_dir, "luatdansu_qas.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_qas, f, ensure_ascii=False, indent=4)

        print(f"Saved {len(all_qas)} QAs to {output_file}")

        self.close_driver()
        print("Crawling completed successfully!")

if __name__ == "__main__":
    crawler = QALawCrawler(headless = True)
    crawler.crawl_all_queries(
        num_pages=2,
        output_dir="data/raw_data"
    )

            





