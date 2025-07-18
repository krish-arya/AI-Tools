import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pandas as pd
import matplotlib.pyplot as plt
from typing import List
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests
from textwrap import wrap
import json
import streamlit as st
import os
from dotenv import load_dotenv
import re
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import shutil

load_dotenv()

def setup_chrome_driver():
    """
    Sets up Chrome driver with proper paths for Render deployment
    """
    chrome_options = uc.ChromeOptions()
    
    # Essential Chrome options for headless server environment
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-field-trial-config")
    chrome_options.add_argument("--disable-back-forward-cache")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-hang-monitor")
    chrome_options.add_argument("--disable-prompt-on-repost")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--metrics-recording-only")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--safebrowsing-disable-auto-update")
    chrome_options.add_argument("--enable-automation")
    chrome_options.add_argument("--password-store=basic")
    chrome_options.add_argument("--use-mock-keychain")
    chrome_options.add_argument("--single-process")  # Add this for Render
    chrome_options.add_argument("--disable-setuid-sandbox")  # Add this for Render
    
    # Memory optimization
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # Render-specific Chrome binary path detection
    chrome_binary_paths = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium", 
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/snap/bin/chromium",
        "/usr/local/bin/chromium",
        "/usr/local/bin/google-chrome"
    ]
    
    # Find available Chrome binary
    chrome_binary = None
    for path in chrome_binary_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            chrome_binary = path
            print(f"✅ Found Chrome binary at: {path}")
            break
    
    if not chrome_binary:
        # Try using shutil.which to find Chrome
        chrome_binary = shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")
        if chrome_binary:
            print(f"✅ Found Chrome binary via which: {chrome_binary}")
    
    if chrome_binary:
        chrome_options.binary_location = chrome_binary
    else:
        raise FileNotFoundError(
            "Chrome browser not found. Please ensure chromium-browser is installed via apt.txt"
        )
    
    # Chrome driver path detection
    chromedriver_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/snap/bin/chromedriver",
        "/usr/bin/chromium-chromedriver"
    ]
    
    chromedriver_path = None
    for path in chromedriver_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            chromedriver_path = path
            print(f"✅ Found ChromeDriver at: {path}")
            break
    
    if not chromedriver_path:
        chromedriver_path = shutil.which("chromedriver") or shutil.which("chromium-chromedriver")
        if chromedriver_path:
            print(f"✅ Found ChromeDriver via which: {chromedriver_path}")
    
    try:
        # Try to create driver with specific paths
        if chromedriver_path:
            driver = uc.Chrome(options=chrome_options, driver_executable_path=chromedriver_path)
            print(f"✅ ChromeDriver initialized with path: {chromedriver_path}")
        else:
            # Let undetected_chromedriver handle driver path automatically
            driver = uc.Chrome(options=chrome_options)
            print("✅ ChromeDriver initialized automatically")
        
        return driver
        
    except Exception as e:
        print(f"❌ Chrome driver initialization failed: {e}")
        # Try with version_main parameter for compatibility
        try:
            driver = uc.Chrome(options=chrome_options, version_main=None)
            print("✅ ChromeDriver initialized with version_main=None")
            return driver
        except Exception as e2:
            print(f"❌ Second attempt failed: {e2}")
            raise Exception(f"Failed to initialize Chrome driver: {e}")

def display_wrapped_json(data, width=80):
    def wrap_str(s):
        return '\n'.join(wrap(s, width=width))
    def process_item(item):
        if isinstance(item, dict):
            return {k: process_item(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [process_item(i) for i in item]
        elif isinstance(item, str):
            return wrap_str(item)
        else:
            return item
    wrapped_data = process_item(data)
    st.code(json.dumps(wrapped_data, indent=2), language='json')
    
def should_skip_url(url):
    skip_keywords = ["/cart", "/checkout", "/login", "/account", "/my-account"]
    if any(kw in url.lower() for kw in skip_keywords):
        return True
    if "?" in url:  # Skip paginated, sorted, filtered variants
        return True
    return False

def get_rendered_html(url, driver=None):
    """
    Updated to use the same Chrome driver setup as main1.py
    """
    try:
        if driver is None:
            # Use the same setup function instead of creating driver manually
            driver = setup_chrome_driver()
            should_quit = True
        else:
            should_quit = False

        driver.get(url)
        time.sleep(2)
        html = driver.page_source
        
        if should_quit:
            driver.quit()
            
        return html

    except Exception as e:
        print(f"❌ Failed to render: {e}")
        if driver and should_quit:
            try:
                driver.quit()
            except:
                pass
        return None

def extract_internal_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    internal_links = set()
    domain = urlparse(base_url).netloc
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("/") or domain in href:
            full_url = urljoin(base_url, href)
            internal_links.add(full_url.split("#")[0])
    return list(internal_links)

def full_seo_audit(url, titles_seen, descs_seen, content_hashes_seen, html):
    result = {}
    visited_urls = set()
    internal_errors = []

    try:
        if not html:
            result["error"] = f"Could not render page: {url}"
            return result

        soup = BeautifulSoup(html, "html.parser")
        anchor_tags = soup.find_all("a", href=True)
        parsed_url = urlparse(url)

        # --- Meta Data ---
        title_tag = soup.find("title")
        desc_tag = soup.find("meta", {"name": "description"})

        title_text = title_tag.text.strip() if title_tag else ""
        desc_text = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

        result["title"] = {
            "text": title_text or "Missing",
            "length": len(title_text),
            "word_count": len(title_text.split()),
        }
        result["description"] = {
            "text": desc_text or "Missing",
            "length": len(desc_text),
            "word_count": len(desc_text.split()),
        }

        # Duplicate Checks
        if title_text in titles_seen:
            result["duplicate_title"] = True
        titles_seen.add(title_text)

        if desc_text in descs_seen:
            result["duplicate_meta_description"] = True
        descs_seen.add(desc_text)

        page_text = " ".join(soup.stripped_strings)
        text_hash = hash(page_text)
        if text_hash in content_hashes_seen:
            result["duplicate_content"] = True
        content_hashes_seen.add(text_hash)

        # Headings
        result["headings"] = {f"H{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)}
        h1_tag = soup.find("h1")
        h1_text = h1_tag.text.strip() if h1_tag else ""
        result["H1_content"] = h1_text
        if h1_text and title_text and h1_text.strip().lower() == title_text.strip().lower():
            result["h1_title_duplicate"] = True
        # --- External (outbound) broken link check ---
        external_broken_links = []
        for a in anchor_tags:
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin(url, href)
            href_netloc = urlparse(full_url).netloc
            if href_netloc and href_netloc != parsed_url.netloc:
                try:
                    resp = requests.head(full_url, timeout=5, allow_redirects=True)
                    if resp.status_code >= 400:
                        external_broken_links.append({
                            "url": full_url,
                            "status": resp.status_code
                        })
                except Exception as e:
                    external_broken_links.append({
                        "url": full_url,
                        "error": str(e)
                    })

        result["external_broken_links"] = external_broken_links     

        # Text Stats
        total_words = len(re.findall(r'\b\w+\b', page_text))
        anchor_tags = soup.find_all("a", href=True)
        anchor_texts = [a.get_text(strip=True) for a in anchor_tags if a.get_text(strip=True)]
        anchor_words = sum(len(a.split()) for a in anchor_texts)

        result["word_stats"] = {
            "total_words": total_words,
            "anchor_words": anchor_words,
            "anchor_ratio_percent": round((anchor_words / total_words) * 100, 2) if total_words else 0,
            "sample_anchors": anchor_texts[:10]
        }

        result["empty_anchor_text_links"] = sum(1 for a in anchor_tags if not a.get_text(strip=True))

        non_descriptive_phrases = {"click here", "read more", "learn more", "more", "here", "view"}
        result["non_descriptive_anchors"] = sum(
            1 for a in anchor_texts if a.lower() in non_descriptive_phrases
        )

        # HTTPS check
        result["https_info"] = {
            "using_https": url.startswith("https://"),
            "was_redirected": False
        }

        if len(anchor_tags) <= 1:
            result["single_internal_link"] = True

        http_links = [urljoin(url, a["href"]) for a in anchor_tags if url.startswith("https://") and urljoin(url, a["href"]).startswith("http://")]
        if http_links:
            result["http_links_on_https"] = http_links

        if parsed_url.query:
            result["url_has_parameters"] = True

        html_size = len(html)
        result["text_to_html_ratio_percent"] = round((len(page_text) / html_size) * 100, 2) if html_size else 0

        result["schema"] = {
            "json_ld_found": bool(soup.find_all("script", {"type": "application/ld+json"})),
            "microdata_found": bool(soup.find_all(attrs={"itemscope": True}))
        }

        images = soup.find_all("img")
        broken_images = []
        for img in images[:10]:
            src = img.get("src")
            if src:
                img_url = urljoin(url, src)
                try:
                    img_resp = requests.head(img_url, timeout=5)
                    if img_resp.status_code >= 400:
                        broken_images.append({"src": src, "status": img_resp.status_code})
                except Exception as e:
                    broken_images.append({"src": src, "error": str(e)})

        result["images"] = {
            "total_images": len(images),
            "images_without_alt": sum(1 for img in images if not img.get("alt")),
            "sample_images": [{"src": img.get("src"), "alt": img.get("alt")} for img in images[:5]],
            "broken_images": broken_images
        }

        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        try:
            robots_response = requests.get(robots_url, timeout=5)
            disallows = [line.strip() for line in robots_response.text.splitlines() if line.lower().startswith("disallow")]
            result["robots_txt"] = {
                "found": True,
                "disallows": disallows
            }
        except:
            result["robots_txt"] = {
                "found": False,
                "disallows": []
            }

        meta_robots = soup.find("meta", {"name": "robots"})
        result["meta_robots"] = meta_robots["content"] if meta_robots and meta_robots.get("content") else ""

        base_domain = parsed_url.netloc
        for a in anchor_tags:
            href = a["href"]
            full_url = urljoin(url, href)
            if urlparse(full_url).netloc == base_domain and full_url not in visited_urls:
                visited_urls.add(full_url)
                try:
                    head_resp = requests.head(full_url, allow_redirects=True, timeout=5)
                    if head_resp.status_code >= 400:
                        internal_errors.append({"url": full_url, "status": head_resp.status_code})
                except Exception as e:
                    internal_errors.append({"url": full_url, "error": str(e)})

        result["internal_link_errors"] = internal_errors

    except Exception as e:
        result["error"] = str(e)

    return result

def ai_analysis(report):
    prompt = f"""You are an advanced SEO and web performance analyst. I am providing a JSON-formatted audit report of a website. This JSON includes data for individual URLs covering:
- HTTP/HTTPS status and response codes (including 4xx and 5xx errors)
- Page speed and response time
- Metadata (title, description, length, duplication)
- Content elements (word count, heading structure, text-to-HTML ratio)
- Link data (internal/external links, anchor text quality, redirects)
- Image data (alt tag presence, broken images)
- Schema markup presence
- Indexing and crawling restrictions (robots.txt, meta robots)

Your response should follow this structure:

### 🧠 AI-Powered SEO Summary

Then provide a detailed analysis, structured into these sections:

1. **Overall Health Summary**
   Brief summary of the site's technical SEO status.

2. **Strengths**
   Highlight technical strengths (e.g. HTTPS, schema usage, fast load times).

3. **Issues to Fix**
    Include only issues that are detected in the audit report.

4. **Critical Page-Level Errors**
   List problematic URLs and their specific technical issues.

5. **Actionable Recommendations**
   Give clear steps to improve technical SEO, indexing, crawlability, and UX.

---

Important:
- Parse the full report without skipping fields.
- Do NOT return your output as JSON.
- Do NOT include triple backticks or code blocks.
- Make the response client-friendly, as if it's going into a formal audit report.
- Maintain clean structure, use bullet points and sections for clarity.

[SEO_REPORT]: {report}
"""

    api_key = os.getenv("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"❌ Error during Gemini API call: {e}\n\nDetails: {response.text}"
