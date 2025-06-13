import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class DetectionConfig:
    def __init__(self):
        self.execution_strategy = 'sequential'
        self.confidence_threshold = 70
        self.max_execution_time = 10
        self.methods = {
            'content_analysis': {'enabled': True, 'weight': 1.0, 'timeout': 2.0},
            'ocr_analysis': {'enabled': False, 'weight': 0.8, 'timeout': 5.0}
        }

    @classmethod
    def content_only_preset(cls):
        """Content analysis only"""
        config = cls()
        config.methods = {
            'content_analysis': {'enabled': True, 'weight': 1.0, 'timeout': 2.0},
            'ocr_analysis': {'enabled': False, 'weight': 0.8, 'timeout': 5.0}
        }
        return config

    @classmethod
    def ocr_enabled_preset(cls):
        """Both content and OCR analysis"""
        config = cls()
        config.methods = {
            'content_analysis': {'enabled': True, 'weight': 1.0, 'timeout': 2.0},
            'ocr_analysis': {'enabled': True, 'weight': 0.8, 'timeout': 5.0}
        }
        return config


class HybridDetectionEngine:
    def __init__(self, config):
        self.config = config

    def analyze_url(self, driver, url, row_index=0):
        """Analyze URL with configured detection methods"""
        start_time = time.time()

        # Always try content analysis first
        if self.config.methods['content_analysis']['enabled']:
            status, reason, confidence, execution_time = content_text_detection(driver, url)

            # If content analysis finds an error, return immediately
            if status == 'FAIL':
                return DetectionResult(status, reason, confidence, execution_time, 'content_analysis')

        # If OCR is enabled and content analysis passed, we can still use OCR later on screenshots
        # But for now, return the content analysis result
        execution_time = int((time.time() - start_time) * 1000)
        return DetectionResult(status, reason, confidence, execution_time, 'content_analysis')


class DetectionResult:
    def __init__(self, status, reason, confidence, execution_time, method_name):
        self.status = status
        self.method_name = method_name
        self.confidence = confidence
        self.execution_time = execution_time
        self.error_message = reason if status == 'FAIL' else None
        self.evidence = {
            'detection_reason': reason,
            'method': method_name,
            'confidence': confidence
        }


def extract_all_modal_and_dialog_content(driver):
    """Enhanced modal and dialog detection with alert handling"""
    try:
        logger.info("🔍 Starting comprehensive modal/dialog detection...")
        all_modal_content = []

        # 1. HIGHEST PRIORITY: Check for JavaScript alerts first
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text.strip()
            logger.info(f"🚨 JAVASCRIPT ALERT FOUND: '{alert_text}'")
            all_modal_content.append(f"JS_ALERT: {alert_text}")

            # Don't accept the alert here - let the caller handle it
            # This allows the fail detection to process it properly

        except:
            logger.debug("No JavaScript alert detected")

        # 2. Check for visible modal/dialog containers
        modal_container_selectors = [
            # Generic modal containers
            "div[style*='display: block']",
            "div[class*='modal'][style*='display: block']",
            "div[class*='dialog'][style*='display: block']",
            "div[class*='popup'][style*='display: block']",

            # Bootstrap modals
            ".modal.show",
            ".modal-dialog",
            ".modal-content",

            # jQuery UI dialogs
            ".ui-dialog:visible",
            ".ui-dialog-content:visible",

            # Generic dialog patterns
            "[role='dialog']:visible",
            "[role='alertdialog']:visible",
        ]

        for selector in modal_container_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.size['height'] > 0:
                        element_text = element.text.strip()
                        if element_text and len(element_text) > 3:
                            all_modal_content.append(f"MODAL_CONTAINER: {element_text}")
                            logger.info(f"📋 MODAL CONTAINER FOUND: '{element_text[:100]}...'")
            except Exception as e:
                logger.debug(f"Error checking modal selector {selector}: {e}")

        # 3. Look for specific fail criteria in visible elements
        fail_criteria = [
            'invalid select file',
            'page does not exist',
            'an exception has occurred',
            'access denied',
            'your request did not complete',
            'exception messages:',
            'please try your request again',
        ]

        for criteria in fail_criteria:
            try:
                xpath = f"//*[contains(text(), '{criteria}')]"
                elements = driver.find_elements(By.XPATH, xpath)
                for element in elements:
                    if element.is_displayed():
                        element_text = element.text.strip()
                        all_modal_content.append(f"FAIL_CRITERIA_FOUND: {element_text}")
                        logger.info(f"🎯 FAIL CRITERIA FOUND: '{element_text}'")
            except:
                continue

        # Combine all found content
        combined_content = "\n".join(all_modal_content)
        logger.info(f"📊 Total modal content sources found: {len(all_modal_content)}")

        return combined_content

    except Exception as e:
        logger.error(f"💥 Error in modal detection: {e}")
        return ""

def is_error_content(text):
    """Enhanced error detection with specific focus on 'Invalid select file'"""
    if not text:
        logger.info("❌ No text to analyze")
        return False

    text_lower = text.lower()
    logger.info(f"🔍 Analyzing text for errors... Length: {len(text)} chars")
    logger.info(f"📝 Text preview: '{text[:150]}...'")

    # HIGHEST PRIORITY: Your specific error (exact match)
    critical_patterns = [
        'invalid select file:',
        'invalid select file',
        'invalid file:',
        'invalid file',
        'invalid select'
    ]

    for pattern in critical_patterns:
        if pattern in text_lower:
            logger.info(f"🚨 CRITICAL ERROR DETECTED: Found '{pattern}' in text")
            return True

    # HIGH PRIORITY: Authentication errors
    auth_patterns = [
        'access denied',
        'unauthorized',
        'permission denied',
        'forbidden',
        'session expired',
        'login required',
        'authentication failed'
    ]

    for pattern in auth_patterns:
        if pattern in text_lower:
            logger.info(f"🔐 AUTH ERROR DETECTED: Found '{pattern}' in text")
            return True

    # MEDIUM PRIORITY: System errors
    system_patterns = [
        'error occurred',
        'exception occurred',
        'not found',
        'database error',
        'connection error',
        'timeout',
        'service unavailable',
        '404', '403', '500', '502', '503'
    ]

    for pattern in system_patterns:
        if pattern in text_lower:
            logger.info(f"⚙️ SYSTEM ERROR DETECTED: Found '{pattern}' in text")
            return True

    logger.info("✅ No error patterns detected in text")
    return False


def extract_error_detail(text):
    """Extract specific error details from text with enhanced logic"""
    if not text:
        return "No error text found"

    text_lower = text.lower()

    # Check for specific error types and return appropriate message
    if 'invalid select file:' in text_lower:
        return "Invalid select file error (with colon)"
    elif 'invalid select file' in text_lower:
        return "Invalid select file error"
    elif 'invalid file:' in text_lower:
        return "Invalid file error (with colon)"
    elif 'invalid file' in text_lower:
        return "Invalid file error"
    elif 'access denied' in text_lower:
        return "Access denied error"
    elif 'session expired' in text_lower:
        return "Session expired error"
    elif 'not found' in text_lower:
        return "Page not found error"
    elif 'unauthorized' in text_lower:
        return "Unauthorized access error"
    elif 'database error' in text_lower:
        return "Database error"
    else:
        # Look for lines containing error keywords
        lines = text.split('\n')
        for line in lines:
            line_clean = line.strip()
            if line_clean and any(err in line_clean.lower() for err in ['error', 'failed', 'invalid', 'denied']):
                return line_clean[:150]  # Return first meaningful error line

        # Fallback - return first non-empty line
        for line in lines:
            if line.strip():
                return line.strip()[:100]

        return "Error detected but no specific details found"


def content_text_detection(driver, url):
    """Enhanced content-based text analysis with comprehensive modal detection"""
    start_time = time.time()

    try:
        logger.info(f"🌐 Starting enhanced content detection for: {url}")

        # Wait for page to be ready
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Additional wait for any modals/dialogs to appear
        time.sleep(3)
        logger.info("⏰ Page loaded, waiting for modals to appear...")

        # Get comprehensive page content including modals and dialogs
        page_content = extract_all_modal_and_dialog_content(driver)

        # Analyze content for errors
        if is_error_content(page_content):
            execution_time = int((time.time() - start_time) * 1000)
            error_detail = extract_error_detail(page_content)
            logger.info(f"❌ ERROR DETECTED: {error_detail}")
            return "FAIL", error_detail, 98, execution_time

        # Check page title for errors
        try:
            title = driver.title.lower() if driver.title else ""
            title_error_patterns = ['error', 'invalid', 'denied', 'unauthorized', '404', '403', '500']

            for pattern in title_error_patterns:
                if pattern in title:
                    execution_time = int((time.time() - start_time) * 1000)
                    logger.info(f"❌ ERROR IN TITLE: Found '{pattern}' in title '{driver.title}'")
                    return "FAIL", f"Error in page title: {driver.title}", 90, execution_time

        except Exception as e:
            logger.debug(f"Error checking title: {e}")

        # Default: PASS
        execution_time = int((time.time() - start_time) * 1000)
        logger.info(f"✅ NO ERRORS DETECTED - Page appears normal")
        return "PASS", "No errors detected", 85, execution_time

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        error_msg = f"Detection error: {str(e)[:100]}"
        logger.error(f"💥 DETECTION FAILED: {error_msg}")
        return "FAIL", error_msg, 70, execution_time


def extract_all_text_content(driver):
    """Legacy function - now uses enhanced modal detection"""
    return extract_all_modal_and_dialog_content(driver)


# Simplified function names for backward compatibility
def simple_detection(driver, url):
    return content_text_detection(driver, url)


def text_only_detection(driver, url):
    return content_text_detection(driver, url)