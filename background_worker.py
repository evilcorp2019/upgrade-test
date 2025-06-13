import time
import os
import pandas as pd
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from database import DatabaseManager, TestRun
from datetime import datetime
import logging
import json
import sys

# Import detection system
try:
    from detection_engine import DetectionConfig

    HYBRID_DETECTION_AVAILABLE = True
except ImportError:
    HYBRID_DETECTION_AVAILABLE = False

# Fix console encoding
if sys.platform == "win32":
    try:
        import codecs

        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer)
    except:
        pass

# Simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('worker.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HybridBackgroundWorker:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.screenshots_dir = "screenshots"
        self.sessions_dir = "sessions"
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.sessions_dir, exist_ok=True)

        # Essential settings only
        self.HYBRID_DETECTION_ENABLED = HYBRID_DETECTION_AVAILABLE
        self.PAGE_LOAD_TIMEOUT = 10
        self.BATCH_DB_OPERATIONS = True
        self.DB_BATCH_SIZE = 5
        self.pending_results = []
        self.last_db_batch_time = time.time()

        logger.info("AGGRESSIVE Error Detection Worker initialized")

    def create_ultra_fast_browser(self):
        """Create browser optimized for SPEED"""
        try:
            logger.info("Creating FAST browser...")

            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")

            # Speed optimizations
            chrome_options.add_argument("--disable-logging")
            chrome_options.add_argument("--disable-gpu-logging")
            chrome_options.add_argument("--log-level=3")

            # Smaller window for faster rendering
            chrome_options.add_argument("--window-size=1024,768")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # FASTER timeouts
            driver.set_page_load_timeout(8)  # Reduced from 10
            driver.implicitly_wait(1)  # Reduced from 3

            logger.info("FAST browser created successfully")
            return driver

        except Exception as e:
            logger.error(f"Failed to create browser: {e}")
            return None

    def get_pending_jobs_fast(self):
        try:
            return self.db_manager.session.query(TestRun).filter(
                TestRun.status.in_(['pending', 'waiting_login'])
            ).order_by(TestRun.created_date).limit(10).all()
        except Exception as e:
            logger.error(f"Error getting pending jobs: {e}")
            return []

    def flush_pending_results(self, force=False):
        if not self.pending_results:
            return

        if force or len(self.pending_results) >= self.DB_BATCH_SIZE:
            try:
                for result_data in self.pending_results:
                    self.db_manager.add_test_result(**result_data)
                self.db_manager.session.commit()
                logger.debug(f"📦 Batched {len(self.pending_results)} database operations")
                self.pending_results.clear()
            except Exception as e:
                logger.error(f"Batch operation failed: {e}")
                self.pending_results.clear()

    def add_result_to_batch(self, **kwargs):
        self.pending_results.append(kwargs)

    def load_urls_from_file(self, test_run):
        try:
            file_path = f"uploads/{test_run.uploaded_filename}"
            if not os.path.exists(file_path):
                logger.error(f"Uploaded file not found: {file_path}")
                return None

            if test_run.uploaded_filename.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            # Filter out rows with empty URLs
            df = df.dropna(subset=[test_run.url_column])
            logger.info(f"Loaded {len(df)} rows from file")
            return df
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None

    def simple_fail_detection(self, driver, url, max_wait_time=5):
        """Enhanced logic: Check for alerts and fail criteria"""
        logger.debug(f"🔍 Checking fail criteria for: {url}")

        start_time = time.time()

        # Check immediately and then at 2 and 4 seconds to catch delayed alerts/modals
        check_intervals = [0.5, 2, 4]

        for wait_seconds in check_intervals:
            if time.time() - start_time > max_wait_time:
                break

            # Wait for the interval (except first check)
            if wait_seconds > 0.5:
                time.sleep(wait_seconds - check_intervals[check_intervals.index(wait_seconds) - 1])

            # Check for fail criteria (including alerts)
            fail_result = self.check_fail_criteria(driver)

            if fail_result['is_fail']:
                logger.info(f"❌ FAIL detected at {wait_seconds}s: {fail_result['reason']}")
                return True, fail_result['reason'], 95
            else:
                logger.debug(f"✅ No fail criteria found at {wait_seconds}s")

        logger.debug("✅ No fail criteria detected - URL PASSED")
        return False, "No fail criteria detected", 85


    # def check_fail_criteria(self, driver):
    #     """Expandable fail criteria checker - ADD NEW FAIL TEXTS HERE"""
    #
    #     # FAIL CRITERIA LIST - ADD NEW FAIL TEXTS HERE
    #     fail_criteria = [
    #         'invalid select file',
    #         'page does not exist',
    #         'an exception has occurred',
    #         'access denied',
    #         'your request did not complete',
    #         'exception messages:',
    #         'please try your request again',
    #     ]
    #
    #     try:
    #         # Method 1: Check page source (fastest)
    #         page_source = driver.page_source.lower()
    #
    #         # DEBUG: Log what we're looking for and what we found
    #         logger.info(f"🔍 DEBUG: Checking {len(fail_criteria)} fail criteria")
    #         logger.info(f"🔍 DEBUG: Page source length: {len(page_source)}")
    #
    #         # Check each criteria individually and log results
    #         for criteria in fail_criteria:
    #             found_in_source = criteria in page_source
    #             logger.info(f"🔍 DEBUG: '{criteria}' in page source: {found_in_source}")
    #
    #             if found_in_source:
    #                 logger.info(f"🎯 FAIL criteria '{criteria}' found in page source")
    #                 return {
    #                     'is_fail': True,
    #                     'reason': f"Found: {criteria}",
    #                     'criteria': criteria
    #                 }
    #
    #         # Method 2: Check body text
    #         body = driver.find_element(By.TAG_NAME, "body")
    #         body_text = body.text.lower()
    #
    #         logger.info(f"🔍 DEBUG: Body text length: {len(body_text)}")
    #         logger.info(f"🔍 DEBUG: Body text preview: {body_text[:200]}")
    #
    #         for criteria in fail_criteria:
    #             found_in_body = criteria in body_text
    #             logger.info(f"🔍 DEBUG: '{criteria}' in body text: {found_in_body}")
    #
    #             if found_in_body:
    #                 logger.info(f"🎯 FAIL criteria '{criteria}' found in body text")
    #                 return {
    #                     'is_fail': True,
    #                     'reason': f"Found: {criteria}",
    #                     'criteria': criteria
    #                 }
    #
    #         # Method 3: Check for JavaScript alerts (existing code)
    #         try:
    #             alert = driver.switch_to.alert
    #             alert_text = alert.text.lower()
    #             for criteria in fail_criteria:
    #                 if criteria in alert_text:
    #                     logger.info(f"🎯 FAIL criteria '{criteria}' found in alert")
    #                     alert.accept()
    #                     return {
    #                         'is_fail': True,
    #                         'reason': f"Found in alert: {criteria}",
    #                         'criteria': criteria
    #                     }
    #         except:
    #             pass  # No alert present
    #
    #     except Exception as e:
    #         logger.debug(f"Error checking fail criteria: {e}")
    #
    #     logger.info("🔍 DEBUG: No fail criteria found - returning PASS")
    #     return {'is_fail': False, 'reason': None, 'criteria': None}

    def check_fail_criteria(self, driver):
        """Enhanced fail criteria checker with alert detection"""

        # FAIL CRITERIA LIST
        fail_criteria = [
            'invalid select file',
            'page does not exist',
            'an exception has occurred',
            'access denied',
            'your request did not complete',
            'exception messages:',
            'please try your request again',
        ]

        try:
            # Method 1: Check for JavaScript alerts FIRST (highest priority)
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text.strip()
                logger.info(f"🚨 JavaScript alert detected: '{alert_text}'")

                # Check if alert contains any fail criteria (especially "Access denied")
                alert_lower = alert_text.lower()
                for criteria in fail_criteria:
                    if criteria in alert_lower:
                        logger.info(f"🎯 ALERT FAIL criteria '{criteria}' found in alert: '{alert_text}'")
                        alert.accept()  # Accept the alert to close it
                        return {
                            'is_fail': True,
                            'reason': f"Alert: {alert_text}",
                            'criteria': criteria
                        }

                # Even if no specific criteria match, "access denied" in alert should fail
                if 'access denied' in alert_lower or 'denied' in alert_lower:
                    logger.info(f"🎯 ACCESS DENIED alert detected: '{alert_text}'")
                    alert.accept()
                    return {
                        'is_fail': True,
                        'reason': f"Access denied alert: {alert_text}",
                        'criteria': 'access denied'
                    }

                # Alert exists but no fail criteria - accept it and continue
                alert.accept()
                logger.info(f"ℹ️ Alert accepted (no fail criteria): '{alert_text}'")

            except:
                # No alert present, continue with other checks
                pass

            # Method 2: Check page source
            page_source = driver.page_source.lower()
            logger.info(f"🔍 DEBUG: Checking {len(fail_criteria)} fail criteria in page source")
            logger.info(f"🔍 DEBUG: Page source length: {len(page_source)}")

            for criteria in fail_criteria:
                if criteria in page_source:
                    logger.info(f"🎯 FAIL criteria '{criteria}' found in page source")
                    return {
                        'is_fail': True,
                        'reason': f"Found in page: {criteria}",
                        'criteria': criteria
                    }

            # Method 3: Check body text
            body = driver.find_element(By.TAG_NAME, "body")
            body_text = body.text.lower()

            logger.info(f"🔍 DEBUG: Body text length: {len(body_text)}")

            for criteria in fail_criteria:
                if criteria in body_text:
                    logger.info(f"🎯 FAIL criteria '{criteria}' found in body text")
                    return {
                        'is_fail': True,
                        'reason': f"Found in body: {criteria}",
                        'criteria': criteria
                    }

            # Method 4: Check for specific modal/dialog elements that might contain errors
            modal_selectors = [
                "div[class*='modal']",
                "div[class*='dialog']",
                "div[class*='popup']",
                "div[class*='alert']",
                ".ui-dialog-content",
                "[role='dialog']",
                "[role='alertdialog']"
            ]

            for selector in modal_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            element_text = element.text.lower()
                            if element_text:
                                for criteria in fail_criteria:
                                    if criteria in element_text:
                                        logger.info(f"🎯 FAIL criteria '{criteria}' found in modal: {selector}")
                                        return {
                                            'is_fail': True,
                                            'reason': f"Found in modal: {criteria}",
                                            'criteria': criteria
                                        }
                except:
                    continue

        except Exception as e:
            logger.debug(f"Error checking fail criteria: {e}")

        logger.info("🔍 DEBUG: No fail criteria found - returning PASS")
        return {'is_fail': False, 'reason': None, 'criteria': None}

    def process_url_fast(self, driver, url, row_idx, test_run_id, test_screenshot_dir):
        """Fast URL processing: FAIL if criteria found, otherwise PASS"""
        start_time = time.time()

        try:
            logger.debug(f"🔍 Processing: {url}")

            # Navigate to URL
            driver.get(url)
            time.sleep(1)  # Minimal wait

            # Check for fail criteria
            is_fail, reason, confidence = self.simple_fail_detection(driver, url)

            if is_fail:
                status = 'FAIL'
                error_message = reason
                logger.debug(f"❌ FAIL: {reason}")
            else:
                status = 'PASS'
                error_message = None
                logger.debug(f"✅ PASS")

            # Take screenshot
            screenshot_filename = self.take_screenshot_fast(
                driver, test_run_id, row_idx, status, test_screenshot_dir
            )

            execution_time = int((time.time() - start_time) * 1000)
            return status, screenshot_filename, error_message, confidence

        except Exception as e:
            logger.error(f"❌ Navigation failed for {url}: {e}")
            return 'FAIL', None, f"Navigation error: {str(e)[:50]}", 30

    def take_screenshot_fast(self, driver, test_run_id, row_idx, status, test_screenshot_dir):
        """Fast screenshot capture"""
        timestamp = int(time.time())
        screenshot_filename = f"screenshot_{test_run_id}_{row_idx + 1}_{status}_{timestamp}.png"
        screenshot_path = os.path.join(test_screenshot_dir, screenshot_filename)

        try:
            driver.save_screenshot(screenshot_path)
            if os.path.exists(screenshot_path):
                return screenshot_filename
            else:
                return None
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")
            return None

    def wait_for_authentication_fast(self, test_run):
        """Fixed authentication waiting - don't wait here, files should already exist"""
        auth_file = f"sessions/auth_ready_{test_run.id}.txt"
        session_file = f"sessions/session_data_{test_run.id}.json"

        logger.info(f"🔐 Processing authentication for test {test_run.id}")

        # Files should already exist when this is called
        if not (os.path.exists(auth_file) and os.path.exists(session_file)):
            logger.error(f"❌ Session files not found for test {test_run.id}")
            return None

        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)

            logger.info(f"📦 Session data loaded: {len(session_data.get('cookies', []))} cookies")

            driver = self.create_testing_browser_with_session(session_data)
            if driver:
                try:
                    os.remove(auth_file)
                    os.remove(session_file)
                    logger.info("🧹 Session files cleaned up")
                except:
                    pass
                return driver
        except Exception as e:
            logger.error(f"Session processing error: {e}")

        return None

    def create_testing_browser_with_session(self, session_data):
        """Create testing browser with session - FIXED VERSION"""
        try:
            logger.info("🚀 Creating testing browser with session data...")

            driver = self.create_ultra_fast_browser()
            if not driver:
                logger.error("❌ Failed to create base browser")
                return None

            # Get domain from session data
            domain_url = session_data.get('current_url', 'https://www.yardipcv.com')
            base_url = '/'.join(domain_url.split('/')[:3])

            logger.info(f"🌐 Navigating to base URL: {base_url}")
            driver.get(base_url)
            time.sleep(3)  # Wait for initial page load

            # Apply session data
            success = self.apply_session_data_to_browser(driver, session_data)

            if success:
                # Test the session by navigating to the original URL
                test_url = session_data.get('current_url', base_url)
                logger.info(f"🧪 Testing session with URL: {test_url}")
                driver.get(test_url)
                time.sleep(5)  # Wait for page load

                # Verify session worked
                page_title = driver.title.lower() if driver.title else ""
                logger.info(f"📄 Page title after session application: {driver.title}")

                # Check if we're still on a login page
                login_indicators = ['login', 'sign in', 'authenticate', 'invalid']
                if any(indicator in page_title for indicator in login_indicators):
                    logger.warning("⚠️ Session transfer may have failed - still on login page")
                    logger.warning(f"Title: {driver.title}")
                    # Don't quit the browser - return it anyway as it might still work
                    return driver
                else:
                    logger.info(f"✅ Session verified successfully: {driver.title}")
                    return driver
            else:
                logger.error("❌ Failed to apply session data")
                driver.quit()
                return None

        except Exception as e:
            logger.error(f"💥 Failed to create testing browser: {e}")
            if 'driver' in locals():
                try:
                    driver.quit()
                except:
                    pass
            return None

    def apply_session_data_to_browser(self, driver, session_data):
        """Apply session data to browser - ENHANCED VERSION"""
        try:
            logger.info("🔧 Applying session data to testing browser...")

            # Apply cookies
            cookies = session_data.get('cookies', [])
            applied_cookies = 0
            failed_cookies = 0

            for cookie in cookies:
                try:
                    # Clean up cookie data for Selenium
                    cookie_dict = {
                        'name': cookie['name'],
                        'value': cookie['value'],
                    }

                    # Add optional fields if they exist and are valid
                    if cookie.get('domain'):
                        cookie_dict['domain'] = cookie['domain']
                    if cookie.get('path'):
                        cookie_dict['path'] = cookie['path']
                    else:
                        cookie_dict['path'] = '/'

                    # Add security flags if present
                    if 'secure' in cookie:
                        cookie_dict['secure'] = cookie['secure']
                    if 'httpOnly' in cookie:
                        cookie_dict['httpOnly'] = cookie['httpOnly']

                    driver.add_cookie(cookie_dict)
                    applied_cookies += 1

                except Exception as e:
                    failed_cookies += 1
                    logger.debug(f"Could not apply cookie {cookie.get('name', 'unknown')}: {e}")
                    continue

            logger.info(f"🍪 Applied {applied_cookies}/{len(cookies)} cookies ({failed_cookies} failed)")

            # Apply localStorage if available
            local_storage = session_data.get('local_storage', {})
            if local_storage:
                try:
                    for key, value in local_storage.items():
                        # Escape quotes in the value
                        escaped_value = str(value).replace("'", "\\'").replace('"', '\\"')
                        script = f"window.localStorage.setItem('{key}', '{escaped_value}');"
                        driver.execute_script(script)
                    logger.info(f"💾 Applied {len(local_storage)} localStorage items")
                except Exception as e:
                    logger.warning(f"Could not apply localStorage: {e}")

            # Apply sessionStorage if available
            session_storage = session_data.get('session_storage', {})
            if session_storage:
                try:
                    for key, value in session_storage.items():
                        escaped_value = str(value).replace("'", "\\'").replace('"', '\\"')
                        script = f"window.sessionStorage.setItem('{key}', '{escaped_value}');"
                        driver.execute_script(script)
                    logger.info(f"🗂️ Applied {len(session_storage)} sessionStorage items")
                except Exception as e:
                    logger.warning(f"Could not apply sessionStorage: {e}")

            logger.info("✅ Session data application completed")
            return True

        except Exception as e:
            logger.error(f"💥 Failed to apply session data: {e}")
            return False

    def check_browser_health_fast(self, driver):
        """Quick browser health check"""
        try:
            # Simple check - try to get current URL
            current_url = driver.current_url
            return True
        except Exception as e:
            logger.debug(f"Browser health check failed: {e}")
            return False

    def get_or_create_authenticated_driver(self, test_run):
        """Get authenticated driver"""
        if hasattr(self, '_persistent_testing_browser'):
            try:
                title = self._persistent_testing_browser.title
                if not any(indicator in title.lower() for indicator in ['login', 'sign in', 'authenticate']):
                    return self._persistent_testing_browser
                else:
                    self._persistent_testing_browser.quit()
                    delattr(self, '_persistent_testing_browser')
            except:
                if hasattr(self, '_persistent_testing_browser'):
                    delattr(self, '_persistent_testing_browser')

        driver = self.wait_for_authentication_fast(test_run)
        if driver:
            self._persistent_testing_browser = driver
        return driver

    def process_test_run_fast(self, test_run):
        """Process test run with AGGRESSIVE detection - COMPLETE FIXED VERSION"""
        try:
            # Update status to running
            self.db_manager.update_test_run_status(test_run.id, 'running', 0)
            logger.info(f"🔥 Starting AGGRESSIVE processing for test {test_run.id}: {test_run.test_name}")

            # Get authenticated driver - FIXED to not wait indefinitely
            driver = self.wait_for_authentication_fast(test_run)
            if not driver:
                logger.error(f"❌ Failed to get authenticated driver for test {test_run.id}")
                self.db_manager.update_test_run_status(test_run.id, 'failed', 0)
                return

            # Load URLs from uploaded file
            df = self.load_urls_from_file(test_run)
            if df is None:
                logger.error(f"❌ Failed to load URLs from file for test {test_run.id}")
                self.db_manager.update_test_run_status(test_run.id, 'failed', 0)
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                return

            # Setup screenshot directory
            test_screenshot_dir = os.path.join(self.screenshots_dir, f"test_{test_run.id}")
            os.makedirs(test_screenshot_dir, exist_ok=True)

            # Initialize counters
            passed = failed = skipped = 0
            total_urls = len(df)

            logger.info(f"🔥 Processing {total_urls} URLs with AGGRESSIVE ERROR DETECTION")
            logger.info(f"🔥 Will wait up to 3 seconds per URL for errors to appear")

            # In the URL processing loop, change this part:
            for idx, row in df.iterrows():
                try:
                    url = str(row[test_run.url_column])

                    if not url or url == 'nan' or not url.startswith('http'):
                        skipped += 1
                        continue

                    logger.info(f"🔥 Processing URL {idx + 1}/{total_urls}: {url[:50]}...")

                    # FASTER processing with reduced waits
                    status, screenshot_filename, error_message, confidence = self.process_url_fast(
                        driver, url, idx, test_run.id, test_screenshot_dir
                    )

                    # Update counters
                    if status == 'PASS':
                        passed += 1
                    elif status == 'FAIL':
                        failed += 1
                    else:
                        skipped += 1

                    # Get page title quickly
                    try:
                        page_title = driver.title[:100] if driver.title else None  # Reduced length
                    except:
                        page_title = None

                    # Add result to batch
                    self.add_result_to_batch(
                        test_run_id=test_run.id,
                        row_number=idx,
                        url=url,
                        status=status,
                        screenshot_filename=screenshot_filename,
                        page_title=page_title,
                        error_message=error_message,
                        confidence=confidence,
                        execution_time=0,
                        detection_method='fast_invalid_file_detection',
                        evidence=error_message,
                        methods_used='invalid_select_file_only'
                    )

                    # Update progress every 5 URLs instead of every 2
                    if (idx + 1) % 5 == 0:
                        progress = ((idx + 1) / total_urls) * 100
                        self.db_manager.update_test_run_status(test_run.id, 'running', progress)
                        self.flush_pending_results()

                    # Simplified progress logging
                    if (idx + 1) % 10 == 0:  # Log every 10 URLs instead of every URL
                        progress = ((idx + 1) / total_urls) * 100
                        logger.info(f"🔥 Progress: {idx + 1}/{total_urls} ({progress:.0f}%) - P:{passed} F:{failed}")

                    # Remove browser health checks for speed
                    # if not self.check_browser_health_fast(driver): # COMMENTED OUT

                except Exception as e:
                    logger.error(f"💥 Error processing row {idx}: {e}")
                    failed += 1
                    continue

            # Final flush of any remaining results
            self.flush_pending_results(force=True)

            # Calculate final statistics
            total_processed = passed + failed
            success_rate = (passed / total_processed * 100) if total_processed > 0 else 0

            logger.info(f"🔥 Test {test_run.id} processing completed!")
            logger.info(f"🔥 Final Results: P:{passed} F:{failed} S:{skipped} ({success_rate:.1f}% success)")

            # Update test run with final results
            try:
                # Update status to completed
                self.db_manager.update_test_run_status(test_run.id, 'completed', 100.0)

                # Update the test run record with final statistics
                test_run.passed = passed
                test_run.failed = failed
                test_run.skipped = skipped
                test_run.success_rate = success_rate
                test_run.completed_date = datetime.now()
                test_run.status = 'completed'

                # Commit the changes
                self.db_manager.session.commit()

                logger.info(f"✅ Test run {test_run.id} marked as completed in database")

            except Exception as e:
                logger.error(f"💥 Error updating final test results: {e}")
                # Try to at least mark as completed
                try:
                    self.db_manager.update_test_run_status(test_run.id, 'completed', 100.0)
                except:
                    pass

            # Clean up browser
            try:
                if driver:
                    logger.info("🧹 Cleaning up browser...")
                    # Don't quit if this is a persistent browser - just log
                    if hasattr(self, '_persistent_testing_browser') and driver == self._persistent_testing_browser:
                        logger.info("🔄 Keeping persistent browser for future tests")
                    else:
                        driver.quit()
                        logger.info("🔚 Browser closed")
            except Exception as e:
                logger.warning(f"⚠️ Error during browser cleanup: {e}")

            logger.info(f"🎉 Test {test_run.id} completed successfully!")

        except Exception as e:
            logger.error(f"💥 Fatal error in process_test_run_fast: {e}")

            # Try to mark test as failed
            try:
                self.db_manager.update_test_run_status(test_run.id, 'failed', 0)
            except:
                pass

            # Flush any pending results
            try:
                self.flush_pending_results(force=True)
            except:
                pass

            # Clean up browser
            try:
                if 'driver' in locals() and driver:
                    driver.quit()
            except:
                pass

        finally:
            # Ensure any remaining results are saved
            try:
                self.flush_pending_results(force=True)
            except Exception as e:
                logger.error(f"💥 Final flush failed: {e}")

    def process_pending_to_waiting_fast(self, test_run):
        try:
            self.db_manager.update_test_run_status(test_run.id, 'waiting_login', 5.0)
            return True
        except:
            return False


    def cleanup_persistent_session(self):
        """Clean up persistent browser sessions"""
        if hasattr(self, '_persistent_testing_browser'):
            try:
                logger.info("🔚 Cleaning up persistent testing browser...")
                self._persistent_testing_browser.quit()
                delattr(self, '_persistent_testing_browser')
                logger.info("✅ Persistent testing browser cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up persistent testing browser: {e}")

        # Also clean up any old persistent_driver references (backward compatibility)
        if hasattr(self, '_persistent_driver'):
            try:
                logger.info("🔚 Cleaning up old persistent driver...")
                self._persistent_driver.quit()
                delattr(self, '_persistent_driver')
                logger.info("✅ Old persistent driver cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up old persistent driver: {e}")

    def run_hybrid(self):
        """Main worker loop - FIXED VERSION"""
        logger.info("🔥" + "=" * 80)
        logger.info("🔥 AGGRESSIVE ERROR DETECTION WORKER STARTED!")
        logger.info("🔥 This version will:")
        logger.info("🔥   • Wait up to 15 seconds for errors to appear")
        logger.info("🔥   • Check page source, visible text, alerts, title, body, URL")
        logger.info("🔥   • Look specifically for 'Invalid select file'")
        logger.info("🔥   • Use 7 different detection methods per URL")
        logger.info("🔥" + "=" * 80)

        loop_count = 0

        try:
            while True:
                try:
                    loop_count += 1

                    # Log every 10 loops (45 seconds) to show worker is alive
                    if loop_count % 10 == 1:
                        logger.info(f"🔄 Worker alive - Loop #{loop_count}")

                    # Get pending jobs
                    pending_jobs = self.get_pending_jobs_fast()

                    if pending_jobs:
                        logger.info(f"📋 Found {len(pending_jobs)} pending jobs")

                        for job in pending_jobs:
                            logger.info(f"🔍 Processing job {job.id}: {job.test_name} - Status: {job.status}")

                            if job.status == 'pending':
                                # Move to waiting_login
                                if self.process_pending_to_waiting_fast(job):
                                    logger.info(f"📝 Job {job.id} moved to waiting_login")
                                else:
                                    logger.error(f"❌ Failed to move job {job.id} to waiting_login")

                            elif job.status == 'waiting_login':
                                logger.info(f"🔐 Job {job.id} waiting for authentication...")

                                # Check for session files
                                auth_file = f"sessions/auth_ready_{job.id}.txt"
                                session_file = f"sessions/session_data_{job.id}.json"

                                auth_exists = os.path.exists(auth_file)
                                session_exists = os.path.exists(session_file)

                                if auth_exists and session_exists:
                                    logger.info(f"🎯 Authentication files found for job {job.id}!")
                                    logger.info(f"🚀 Starting processing for job {job.id}")
                                    self.process_test_run_fast(job)
                                else:
                                    if loop_count % 20 == 1:  # Log every minute
                                        logger.info(f"⏰ Still waiting for authentication for job {job.id}")
                                        logger.info(f"   Auth file ({auth_file}): {auth_exists}")
                                        logger.info(f"   Session file ({session_file}): {session_exists}")
                    else:
                        # No pending jobs
                        if loop_count % 20 == 1:  # Log every minute when idle
                            logger.info("😴 No pending jobs, worker is idle...")

                    # Sleep for 3 seconds between checks
                    time.sleep(3)

                except KeyboardInterrupt:
                    logger.info("🛑 Keyboard interrupt received")
                    break
                except Exception as e:
                    logger.error(f"💥 Worker loop error: {e}")
                    # Don't break - continue running
                    time.sleep(10)

        finally:
            # Cleanup on shutdown
            logger.info("🔚 Shutting down aggressive worker...")
            try:
                self.flush_pending_results(force=True)
                logger.info("✅ Final database flush completed")
            except Exception as e:
                logger.error(f"💥 Error in final flush: {e}")

            try:
                self.cleanup_persistent_session()
                logger.info("✅ Browser session cleaned up")
            except Exception as e:
                logger.error(f"💥 Error cleaning up session: {e}")

            logger.info("🔥 AGGRESSIVE WORKER STOPPED")

    # Use hybrid worker

BackgroundWorker = HybridBackgroundWorker

if __name__ == "__main__":
    try:
        worker = HybridBackgroundWorker()
        worker.run_hybrid()
    except Exception as e:
        logger.error(f"Failed to start aggressive worker: {e}")