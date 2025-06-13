import logging
import streamlit as st
import pandas as pd
import os
import zipfile
import time
import json
import shutil
import re
from datetime import datetime
from io import BytesIO
from PIL import Image
# import yaml
from database import DatabaseManager, User, TestRun

# CORRECT - No Streamlit commands in import section
try:
    from detection_engine import DetectionConfig, HybridDetectionEngine
    HYBRID_DETECTION_AVAILABLE = True
    HYBRID_DETECTION_ERROR = None
except ImportError as e:
    HYBRID_DETECTION_AVAILABLE = False
    # Store error message for later display
    HYBRID_DETECTION_ERROR = str(e)


# Ensure required directories exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("sessions", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)
os.makedirs("browser_sessions", exist_ok=True)

# Page configuration
st.set_page_config(
    page_title="Yardi URL Tester Pro",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced Professional CSS - COMPLETE REPLACEMENT
#  LOAD EXTERNAL CSS FUNCTION
def load_css(file_name):
    """Load CSS from external file"""
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f" CSS file '{file_name}' not found! Make sure it's in the same directory as your app.")
    except Exception as e:
        st.error(f" Error loading CSS: {e}")

#  LOAD THE EXTERNAL CSS
load_css('styles.css')

# Add navigation tab styling
st.markdown("""
<style>
/* Navigation Tab Styling - Multiple selector approach for reliability */
div[data-testid="column"] button[kind="primary"],
div[data-testid="column"] button[data-testid*="baseButton-primary"],
.nav-container button[kind="primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: 2px solid #667eea !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4) !important;
    transform: translateY(-2px) !important;
}

div[data-testid="column"] button[kind="secondary"],
div[data-testid="column"] button[data-testid*="baseButton-secondary"],
.nav-container button[kind="secondary"] {
    background: rgba(255, 255, 255, 0.1) !important;
    color: #a0a0a0 !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    font-weight: 400 !important;
    box-shadow: none !important;
    transform: none !important;
}

/* All navigation buttons base styling */
.nav-container button {
    width: 100% !important;
    padding: 0.75rem 1rem !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
    font-size: 0.9rem !important;
}

/* Hover effects */
div[data-testid="column"] button[kind="primary"]:hover,
.nav-container button[kind="primary"]:hover {
    background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5) !important;
}

div[data-testid="column"] button[kind="secondary"]:hover,
.nav-container button[kind="secondary"]:hover {
    background: rgba(255, 255, 255, 0.15) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
}

/* Navigation container styling */
.nav-container {
    margin-bottom: 2rem;
    padding: 1rem 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

/* Additional fallback selectors */
button[data-baseweb="button"][data-testid*="primary"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}

button[data-baseweb="button"][data-testid*="secondary"] {
    background: rgba(255, 255, 255, 0.1) !important;
    color: #a0a0a0 !important;
}
</style>
""", unsafe_allow_html=True)


# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'dashboard'


# Database manager
@st.cache_resource
def get_db_manager():
    return DatabaseManager()


db_manager = get_db_manager()

# Hardcoded SQL Query


# =============================================================================
# UTILITY FUNCTIONS FOR ERROR PROCESSING
# =============================================================================

def parse_error_message(error_message):
    """Parse error message to extract browser error and extracted text separately"""
    if not error_message:
        return None, None

    # Check if extracted text is present
    if '| EXTRACTED:' in error_message:
        parts = error_message.split('| EXTRACTED:', 1)
        browser_error = parts[0].strip()
        extracted_text = parts[1].strip() if len(parts) > 1 else ""
        return browser_error, extracted_text
    else:
        return error_message.strip(), None


def extract_meaningful_error_text(error_text):
    """Extract the most meaningful part of error text for display"""
    if not error_text:
        return None

    # Remove common artifacts and clean up
    cleaned_text = re.sub(r'[^\w\s\.\,\!\?\:\;\-\(\)]', ' ', error_text)
    cleaned_text = ' '.join(cleaned_text.split())  # Remove extra whitespace

    # If text is too long, try to find the most relevant part
    if len(cleaned_text) > 150:
        # Look for sentences with error keywords
        sentences = re.split(r'[\.!\?]', cleaned_text)
        error_keywords = ['error', 'fail', 'invalid', 'denied', 'expired', 'required', 'forbidden']

        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in error_keywords):
                if len(sentence.strip()) > 10:
                    return sentence.strip()[:150]

        # Fallback to first meaningful sentence
        for sentence in sentences:
            if len(sentence.strip()) > 20:
                return sentence.strip()[:150]

    return cleaned_text[:200] if len(cleaned_text) > 200 else cleaned_text

logger = logging.getLogger(__name__)


# =============================================================================
# AUTHENTICATION FUNCTIONS
# =============================================================================

def authenticate_user(username, password):
    """Authenticate user"""
    try:
        user = db_manager.authenticate_user(username, password)
        if user:
            st.session_state.authenticated = True
            st.session_state.user_id = user.id
            st.session_state.username = user.username
            return True
        return False
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return False


def logout():
    """Logout user and clean up"""
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = None
    # Clean up any auth sessions
    cleanup_auth_session()
    st.rerun()


def cleanup_auth_session():
    """Clean up authentication session variables"""
    session_vars = ['auth_step', 'auth_test_id', 'auth_url', 'auth_page', 'browser_info']
    for var in session_vars:
        if var in st.session_state:
            del st.session_state[var]


# =============================================================================
# DATA MANAGEMENT FUNCTIONS
# =============================================================================

def save_uploaded_file(uploaded_file):
    """Save uploaded file and return the filename"""
    try:
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)

        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{st.session_state.user_id}_{timestamp}_{uploaded_file.name}"
        file_path = os.path.join(uploads_dir, filename)

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        return filename
    except Exception as e:
        st.error(f"Error saving file: {e}")
        return None


def delete_single_test(test_id):
    """Delete a single test and all its data"""
    try:
        # Get test details for cleanup
        test_run = db_manager.get_test_run_by_id(test_id)
        if not test_run:
            return False

        # Delete test results first (foreign key constraint)
        results = db_manager.get_test_results(test_id)
        for result in results:
            db_manager.session.delete(result)

        # Delete test run
        db_manager.session.delete(test_run)

        # Delete screenshots folder
        screenshots_dir = f"screenshots/test_{test_id}"
        if os.path.exists(screenshots_dir):
            shutil.rmtree(screenshots_dir)

        db_manager.session.commit()
        return True

    except Exception as e:
        db_manager.session.rollback()
        st.error(f"Error deleting test: {e}")
        return False


def delete_multiple_tests(test_list):
    """Delete multiple tests"""
    try:
        success_count = 0
        for test in test_list:
            if delete_single_test(test.id):
                success_count += 1
        return success_count
    except Exception as e:
        st.error(f"Error deleting multiple tests: {e}")
        return 0


# =============================================================================
# LOGIN PAGE
# =============================================================================

def login_page():
    """Login and registration page - FIXED VERSION - No Welcome Back text"""

    # Centered header without extra containers
    st.markdown("""
    <div style="text-align: center; padding: 2rem 1rem; margin-bottom: 1rem;">
        <h1 style="color: white; font-size: 2.5rem; font-weight: 700; margin: 0;">
            Yardi URL Tester Pro
        </h1>
        <p style="color: #a0a0a0; font-size: 1.1rem; margin-top: 0.5rem;">
            Professional URL Testing Platform with Background Jobs
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Center the entire form area
    col1, col2, col3 = st.columns([1, 1.5, 1])

    with col2:
        # Remove any potential empty containers by using direct tabs
        tab1, tab2 = st.tabs(["Login", "Sign Up"])

        with tab1:
            #  FIXED: Removed "Welcome Back!" text completely
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                # Submit button
                submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

                if submitted:
                    if username and password:
                        if authenticate_user(username, password):
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
                    else:
                        st.warning("Please enter both username and password")

        with tab2:
            #  FIXED: Removed "Join Our Platform" text completely
            with st.form("signup_form"):
                new_username = st.text_input("Username", placeholder="Choose a username")
                new_email = st.text_input("Email", placeholder="your.email@company.com")
                new_password = st.text_input("Password", type="password", placeholder="Choose a secure password")
                confirm_password = st.text_input("Confirm Password", type="password",
                                                 placeholder="Confirm your password")

                submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")

                if submitted:
                    if new_username and new_email and new_password and confirm_password:
                        if new_password != confirm_password:
                            st.error("Passwords do not match")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters")
                        elif db_manager.get_user_by_username(new_username):
                            st.error("Username already exists")
                        else:
                            try:
                                user_id = db_manager.create_user(new_username, new_email, new_password)
                                st.success("Account created successfully! Please login.")
                            except Exception as e:
                                st.error(f"Error creating account: {e}")
                    else:
                        st.warning("Please fill in all fields")

# =============================================================================
# DASHBOARD AND NAVIGATION
# =============================================================================

def dashboard_page():
    """
    Main dashboard page with proper navigation highlighting.
    UPDATED: Removed Page Debug tab and functionality
    """

    # Initialise session state
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"

    # Header
    st.markdown(
        f'<div class="main-header"><h1>Yardi URL Tester Pro</h1>'
        f'<p>Welcome back, {st.session_state.username}!</p></div>',
        unsafe_allow_html=True,
    )

    # Navigation bar - UPDATED: Removed Page Debug tab (now 6 columns instead of 7)
    st.markdown('<div class="nav-container">', unsafe_allow_html=True)
    col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1.5, 1.5, 1.5, 1.5, 1])

    # Helper to decide button type
    def nav_button(label, page_key, *, col, key):
        button_type = "primary" if st.session_state.current_page == page_key else "secondary"
        with col:
            if st.button(label, use_container_width=True, type=button_type, key=key):
                st.session_state.current_page = page_key
                st.rerun()

    # Navigation buttons
    nav_button("Dashboard",   "dashboard",   col=col1, key="nav_dashboard")
    nav_button("New Test",    "new_test",    col=col2, key="nav_new_test")
    nav_button("Test History","history",     col=col3, key="nav_history")

    # Manual Auth needs the dynamic badge
    with col4:
        test_runs = db_manager.get_user_test_runs(st.session_state.user_id)
        waiting = [t for t in test_runs if t.status == "waiting_login"]
        label = f"Manual Auth ({len(waiting)})" if waiting else "Manual Auth"
        button_type = "primary" if st.session_state.current_page == "manual_auth" else "secondary"
        if st.button(label, use_container_width=True, type=button_type, key="nav_manual_auth"):
            st.session_state.current_page = "manual_auth"
            st.rerun()

    nav_button("Download SQL", "sql",   col=col5, key="nav_sql")

    # Logout stays secondary - never marked primary
    with col6:
        if st.button("Logout", use_container_width=True, type="secondary", key="nav_logout"):
            logout()

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")

    # Debug info (remove this after testing)
    # st.caption(f"Current page: {st.session_state.current_page}")

    # Render the selected page - UPDATED: Removed debug page handling
    page = st.session_state.current_page
    if page == "dashboard":
        show_dashboard()
    elif page == "new_test":
        show_new_test()
    elif page == "history":
        show_test_history()
    elif page == "manual_auth":
        show_manual_authentication()
    elif page == "sql":
        show_sql_download()
    elif page == "view_results":
        show_view_results()


def get_button_position(current_page):
    """Get the column position of the active button for CSS targeting - UPDATED: Removed debug"""
    page_positions = {
        'dashboard': 1,
        'new_test': 2,
        'history': 3,
        'manual_auth': 4,
        'sql': 5
    }
    return page_positions.get(current_page, 1)


# =============================================================================
# DASHBOARD OVERVIEW
# =============================================================================

def show_dashboard():
    """Dashboard overview page"""
    st.header("Dashboard Overview")

    # Get user's test runs
    test_runs = db_manager.get_user_test_runs(st.session_state.user_id)

    if not test_runs:
        st.info("Welcome! You haven't run any tests yet. Click 'New Test' to get started.")
        return

    # Statistics
    total_tests = len(test_runs)
    completed_tests = len([t for t in test_runs if t.status == 'completed'])
    running_tests = len([t for t in test_runs if t.status in ['running', 'waiting_login']])
    failed_tests = len([t for t in test_runs if t.status == 'failed'])

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Tests", total_tests)
    with col2:
        st.metric("Completed", completed_tests)
    with col3:
        st.metric("Running", running_tests)
    with col4:
        st.metric("Failed", failed_tests)

    # Recent activity
    st.subheader("Recent Activity")

    recent_tests = test_runs[:5]  # Last 5 tests

    for test in recent_tests:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

            with col1:
                st.write(f"**{test.test_name}**")
                st.caption(f"Database: {test.database_name}")

            with col2:
                if test.status == 'running':
                    st.markdown(f'<div class="job-status-running">Running ({test.progress:.0f}%)</div>',
                                unsafe_allow_html=True)
                elif test.status == 'completed':
                    st.markdown(f'<div class="job-status-completed">Completed</div>', unsafe_allow_html=True)
                elif test.status == 'failed':
                    st.markdown(f'<div class="job-status-failed">Failed</div>', unsafe_allow_html=True)
                elif test.status == 'waiting_login':
                    st.markdown(f'<div class="job-status-waiting">Waiting Auth</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="job-status-pending">Pending</div>', unsafe_allow_html=True)

            with col3:
                st.write(f"Date: {test.created_date.strftime('%Y-%m-%d %H:%M')}")

            with col4:
                if test.status == 'completed':
                    if st.button(f"View", key=f"view_{test.id}"):
                        st.session_state.selected_test_id = test.id
                        st.session_state.current_page = 'view_results'
                        st.rerun()
                elif test.status == 'waiting_login':
                    if st.button(f"Auth", key=f"auth_dash_{test.id}"):
                        st.session_state.current_page = 'manual_auth'
                        st.rerun()

        st.markdown("---")

    # Database summary
    st.subheader("Databases Tested")
    databases = db_manager.get_user_databases(st.session_state.user_id)

    if databases:
        for db_name in databases:
            db_tests = [t for t in test_runs if t.database_name == db_name]
            completed_db_tests = [t for t in db_tests if t.status == 'completed']

            if completed_db_tests:
                avg_success = sum([t.success_rate for t in completed_db_tests]) / len(completed_db_tests)
                st.markdown(f"**{db_name}**: {len(db_tests)} tests, {avg_success:.1f}% avg success rate")


# =============================================================================
# NEW TEST SUBMISSION
# =============================================================================

def show_new_test():
    """New test submission page with detection method section removed"""
    st.header("Submit New URL Test")

    # Step 1: Test Identification - UPDATED
    st.subheader("1. Test Identification")

    col1, col2 = st.columns(2)

    with col1:
        test_name = st.text_input(
            "Test Name *",
            placeholder="e.g., Weekly Property Check, June Maintenance URLs",
            help="Give your test a descriptive name for easy identification"
        )

    with col2:
        # FIXED: Make database name optional
        database_name = st.text_input(
            "Database Name",  # Removed the asterisk
            placeholder="e.g., Production_Yardi, Client_Portal (Optional)",
            help="Enter the database name being tested (optional)"
        )

    # FIXED: Updated validation logic
    if test_name:
        # Auto-generate database name if not provided
        if not database_name:
            database_name = f"Database_{datetime.now().strftime('%Y%m%d')}"

        st.success(f"Test will be saved as: **{test_name}** (Database: {database_name})")
        form_valid = True
    else:
        st.warning("Please provide a test name to continue")
        form_valid = False

    #  REMOVED: Step 2: Detection Method Selection - COMPLETELY REMOVED

    # Step 2: File Upload (renumbered from Step 3)
    st.subheader("2. Upload Data File")

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file with URLs",
        type=['csv', 'xlsx', 'xls'],
        help="Upload the file exported from your database query"
    )

    # Process uploaded file
    if uploaded_file is not None:
        try:
            # Read and preview file
            with st.spinner("Processing file..."):
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

            st.success(f"File loaded: {len(df)} rows, {len(df.columns)} columns")

            # Step 3: Column Selection (renumbered from Step 4)
            st.subheader("3. Select URL Column")

            # Detect potential URL columns
            potential_url_columns = []
            for col in df.columns:
                if any(keyword in col.lower() for keyword in ['url', 'link', 'web', 'site', 'href', 'slink']):
                    potential_url_columns.append(col)

            if potential_url_columns:
                st.info(f"Detected potential URL columns: {', '.join(potential_url_columns)}")

            url_column = st.selectbox(
                "Select the column containing URLs/Links",
                options=df.columns.tolist(),
                index=df.columns.tolist().index(potential_url_columns[0]) if potential_url_columns else 0,
                help="Choose the column that contains the URLs you want to test"
            )

            # Step 4: Preview and Validation (renumbered from Step 5)
            st.subheader("4. Preview & Validation")

            # URL analysis
            valid_urls = df[url_column].dropna().astype(str)
            http_urls = [str(u) for u in valid_urls if str(u).startswith("http")]

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Rows", len(df))
            with col2:
                st.metric("Valid URLs", len(http_urls))
            with col3:
                st.metric("URL Coverage", f"{len(http_urls) / len(df) * 100:.1f}%")

            # Data preview
            st.write("**Data Preview:**")
            preview_df = df.head(3).copy()  # REDUCED from 5 to 3 for speed
            if url_column in preview_df.columns:
                preview_df[url_column] = preview_df[url_column].astype(str).apply(
                    lambda x: x[:40] + "..." if len(str(x)) > 40 else str(x)  # REDUCED from 50 to 40
                )
            st.dataframe(preview_df, use_container_width=True)

            # Sample URLs - REDUCED
            if len(http_urls) > 0:
                with st.expander("Sample URLs to be tested"):
                    sample_urls = http_urls[:5]  # REDUCED from 10 to 5
                    for i, url in enumerate(sample_urls, 1):
                        st.text(f"{i}. {url}")
                    if len(http_urls) > 5:
                        st.text(f"... and {len(http_urls) - 5} more URLs")

                # Step 5: Submit Test (renumbered from Step 6)
                st.subheader("5. Submit Test")

                #  FIXED: Use default detection method (Content Text Analysis only)
                detection_method = "Content Text Analysis"  # Default, no user selection
                detection_config = DetectionConfig.content_only_preset()  # Always use fastest mode

                # FIXED: Faster time estimates
                time_per_url = 2  # Fixed time estimate for content analysis only
                total_time_seconds = time_per_url * len(http_urls)

                if total_time_seconds < 60:
                    time_estimate = f"{total_time_seconds} seconds"
                elif total_time_seconds < 3600:
                    time_estimate = f"{total_time_seconds / 60:.1f} minutes"
                else:
                    time_estimate = f"{total_time_seconds / 3600:.1f} hours"

                # SIMPLIFIED: Show only essential info
                col1, col2 = st.columns(2)
                with col1:
                    st.info(f"**URLs to test**: {len(http_urls)}")
                with col2:
                    st.info(f"**Estimated time**: {time_estimate}")

                # FIXED: Submit button with proper validation
                if form_valid and len(http_urls) > 0:
                    if st.button("Start Test Job", type="primary", use_container_width=True):
                        try:
                            with st.spinner("Submitting test job..."):
                                # Save uploaded file
                                saved_filename = save_uploaded_file(uploaded_file)

                                if not saved_filename:
                                    st.error("Failed to save uploaded file")
                                    return

                                # Save detection configuration (always content-only)
                                config_filename = f"config_{st.session_state.user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                config_path = os.path.join("uploads", config_filename)

                                os.makedirs("uploads", exist_ok=True)

                                config_data = {
                                    'methods': detection_config.methods,
                                    'execution_strategy': detection_config.execution_strategy,
                                    'confidence_threshold': detection_config.confidence_threshold,
                                    'max_execution_time': detection_config.max_execution_time,
                                    'detection_method': detection_method,
                                    'created_at': datetime.now().isoformat()
                                }

                                with open(config_path, 'w') as f:
                                    json.dump(config_data, f, indent=2)

                                # Create test run in database
                                test_run_id = db_manager.create_test_run(
                                    user_id=st.session_state.user_id,
                                    database_name=database_name.strip(),
                                    test_name=test_name.strip(),
                                    total_urls=len(http_urls),
                                    url_column=url_column,
                                    uploaded_filename=saved_filename,
                                    config_filename=config_filename
                                )

                                st.success(f"Test job submitted successfully! Job ID: {test_run_id}")
                                st.info("Go to 'Manual Auth' tab to complete authentication and start testing.")

                                # Auto-redirect after delay
                                time.sleep(2)  # REDUCED from 3 to 2
                                st.session_state.current_page = 'manual_auth'
                                st.rerun()

                        except Exception as e:
                            st.error(f"Error submitting job: {e}")
                            logger.error(f"Job submission error: {e}")
                else:
                    if not form_valid:
                        st.error("Please provide a test name before submitting.")
                    elif len(http_urls) == 0:
                        st.error("No valid HTTP URLs found in the selected column.")

            else:
                st.warning("No valid HTTP URLs found in the selected column.")

        except Exception as e:
            st.error(f"Error reading file: {e}")
            logger.error(f"File reading error: {e}")
    else:
        # Show instructions when no file is uploaded
        st.info("Please upload a CSV or Excel file containing URLs to begin testing.")

        with st.expander("How to prepare your file"):
            st.markdown("""
            1. **Run SQL Query**: Go to 'Download SQL' tab and run the query in your database
            2. **Export Results**: Save the query results as CSV or Excel
            3. **Upload Here**: Select your exported file using the upload button above
            4. **Requirements**:
               - File must be CSV or Excel format
               - Must contain at least one column with URLs
               - URLs should start with `http://` or `https://`
            """)

# =============================================================================
# MANUAL AUTHENTICATION WITH PLAYWRIGHT
# =============================================================================

def show_manual_authentication():
    """Handle manual authentication for pending tests - Fixed for Separate Auth/Test"""
    st.header("Manual Authentication Required")

    # Check for tests waiting for authentication
    test_runs = db_manager.get_user_test_runs(st.session_state.user_id)
    waiting_tests = [t for t in test_runs if t.status == 'waiting_login']

    if not waiting_tests:
        st.info("No tests currently waiting for authentication.")
        if st.button("Back to Dashboard"):
            st.session_state.current_page = 'dashboard'
            st.rerun()
        return

    st.info(f"⚠️ **{len(waiting_tests)} tests require manual SSO authentication before automated testing can begin.**")

    for test in waiting_tests:
        with st.container():
            st.subheader(f" Test: {test.test_name}")

            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                st.info(f"**Database**: {test.database_name}")
                st.info(f"**URLs to test**: {test.total_urls}")
                st.info(f"**Created**: {test.created_date.strftime('%Y-%m-%d %H:%M')}")

            with col2:
                st.metric("⏱️ Status", "Waiting for Auth")
                if test.progress > 0:
                    st.progress(test.progress / 100.0)
                    st.caption(f"Progress: {test.progress:.0f}%")

            with col3:
                # Check if this test is currently being authenticated
                auth_in_progress = (
                        'auth_test_id' in st.session_state and
                        st.session_state.auth_test_id == test.id and
                        'auth_step' in st.session_state
                )

                if auth_in_progress:
                    st.info("Auth in progress...")
                else:
                    if st.button(f"Start Auth", key=f"auth_{test.id}", use_container_width=True, type="primary"):
                        # Clear any existing auth state
                        cleanup_auth_session()

                        # Set up authentication for this test
                        st.session_state.auth_test_id = test.id
                        st.session_state.auth_step = 'browser_opening'

                        # Trigger rerun to start authentication flow
                        st.rerun()

            st.markdown("---")

    # Handle authentication flow if in progress
    if 'auth_step' in st.session_state and 'auth_test_id' in st.session_state:
        show_authentication_flow()


def cleanup_auth_session():
    """Clean up authentication session variables - Enhanced for Separate Auth/Test"""
    session_vars = [
        'auth_step',
        'auth_test_id',
        'auth_url',
        'temp_auth_driver',  # For temporary authentication browser
        'auth_driver',  # Legacy - for backward compatibility
        'driver_info'  # Legacy - for backward compatibility
    ]

    for var in session_vars:
        if var in st.session_state:
            # If it's a driver, quit it first
            if var in ['temp_auth_driver', 'auth_driver'] and hasattr(st.session_state[var], 'quit'):
                try:
                    st.session_state[var].quit()
                except:
                    pass
            del st.session_state[var]


def show_authentication_flow():
    """Separate Auth/Test Browser Implementation - Complete Authentication Flow"""
    st.markdown("---")
    st.header("Authentication in Progress")

    test_id = st.session_state.auth_test_id
    test_run = db_manager.get_test_run_by_id(test_id)

    if not test_run:
        st.error("Test not found")
        return

    # Get first URL for authentication
    try:
        file_path = f"uploads/{test_run.uploaded_filename}"
        if os.path.exists(file_path):
            if test_run.uploaded_filename.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            # Get first valid URL
            first_url = None
            for idx, row in df.iterrows():
                url = str(row[test_run.url_column])
                if url and url != 'nan' and url.lower() != 'none' and url.startswith("http"):
                    first_url = url
                    break

            if not first_url:
                st.error("No valid URL found for authentication")
                return
        else:
            st.error("Uploaded file not found")
            return
    except Exception as e:
        st.error(f"Error reading uploaded file: {e}")
        return

    # Step 1: Open TEMPORARY authentication browser
    if st.session_state.auth_step == 'browser_opening':
        st.info(f" **Authentication URL**: {first_url}")
        st.info(" **Opening temporary authentication browser...**")

        if 'temp_auth_driver' not in st.session_state:
            with st.spinner(" Opening temporary browser for authentication..."):
                try:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options
                    from selenium.webdriver.chrome.service import Service
                    from webdriver_manager.chrome import ChromeDriverManager

                    # Create TEMPORARY authentication browser (separate from testing browser)
                    chrome_options = Options()
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument("--disable-dev-shm-usage")
                    chrome_options.add_argument("--window-size=1200,800")
                    # No remote debugging for temp browser - it's completely separate

                    try:
                        service = Service(ChromeDriverManager().install())
                        temp_driver = webdriver.Chrome(service=service, options=chrome_options)
                        temp_driver.get(first_url)

                        st.session_state.temp_auth_driver = temp_driver
                        st.session_state.auth_step = 'browser_opened'
                        st.success(" Temporary authentication browser opened!")
                        time.sleep(2)
                        st.rerun()

                    except Exception as e:
                        st.error(f" Failed to open temporary browser: {e}")
                        st.error(" Make sure Chrome is installed and try again.")
                        return

                except Exception as e:
                    st.error(f" Browser setup failed: {e}")
                    return

    # Step 2: User completes authentication in temporary browser
    elif st.session_state.auth_step == 'browser_opened':
        st.success(" Temporary authentication browser is open!")

        # Show current page info
        if 'temp_auth_driver' in st.session_state:
            try:
                current_title = st.session_state.temp_auth_driver.title
                current_url = st.session_state.temp_auth_driver.current_url
                st.info(f"🌐 **Current page**: {current_title}")
                st.caption(f"URL: {current_url}")
            except:
                st.warning("Cannot read browser status")

        # Instructions
        with st.container():
            st.markdown("### Complete Authentication in Temporary Browser:")
            st.markdown("""
            1. **Complete SSO login** in the opened browser window
               - Handle any OTP/mobile approval steps  
               - Complete multi-factor authentication
               - Wait for full login completion

            2.  **Navigate to any Yardi page** to verify access
               - Ensure you see normal Yardi content (not login page)

            3.  **Click 'Transfer Session'** below to copy authentication to testing browser

            **Note:** The temporary browser will close after transferring your session.
            """)

        # Test authentication button
        if st.button("Test Current Authentication", use_container_width=True):
            if 'temp_auth_driver' in st.session_state:
                try:
                    page_title = st.session_state.temp_auth_driver.title.lower()
                    if any(indicator in page_title for indicator in ['login', 'sign in', 'authenticate', 'invalid']):
                        st.warning(f"Still on login page: {page_title}")
                        st.warning("Please complete authentication before proceeding.")
                    else:
                        st.success(f"Authentication successful! Page: {st.session_state.temp_auth_driver.title}")
                except Exception as e:
                    st.error(f"Error checking authentication: {e}")

        # Action buttons
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Transfer Session & Start Testing", type="primary", use_container_width=True):
                try:
                    # Verify authentication one more time
                    if 'temp_auth_driver' in st.session_state:
                        page_title = st.session_state.temp_auth_driver.title.lower()
                        if any(indicator in page_title for indicator in
                               ['login', 'sign in', 'authenticate', 'invalid']):
                            st.error(" Still on login page. Please complete authentication first.")
                            return

                    st.session_state.auth_step = 'transferring_session'
                    st.rerun()

                except Exception as e:
                    st.error(f" Error starting session transfer: {e}")

        with col2:
            if st.button(" Cancel Authentication", type="secondary", use_container_width=True):
                # Close temporary browser
                if 'temp_auth_driver' in st.session_state:
                    try:
                        st.session_state.temp_auth_driver.quit()
                        del st.session_state.temp_auth_driver
                    except:
                        pass

                # Reset test status
                db_manager.update_test_run_status(test_id, 'pending', 0.0)

                # Clean up
                cleanup_auth_session()

                st.warning(" Authentication cancelled.")
                time.sleep(2)
                st.session_state.current_page = 'dashboard'
                st.rerun()

    # Step 3: Transfer session from temporary to persistent browser
    elif st.session_state.auth_step == 'transferring_session':
        st.info(" **Transferring authentication session...**")

        try:
            if 'temp_auth_driver' not in st.session_state:
                st.error(" Temporary browser not found")
                return

            # Extract cookies and session data from temporary browser
            with st.spinner("Extracting session data..."):
                session_data = extract_session_data_from_temp_browser(st.session_state.temp_auth_driver)

            if session_data:
                # Create signal files for background worker with session data
                os.makedirs("sessions", exist_ok=True)

                # Session data file
                session_file = f"sessions/session_data_{test_id}.json"
                with open(session_file, 'w') as f:
                    json.dump(session_data, f)

                # Signal file for worker
                auth_file = f"sessions/auth_ready_{test_id}.txt"
                with open(auth_file, 'w') as f:
                    f.write(f"Session transfer completed at {datetime.now()}\n")
                    f.write(f"Test ID: {test_id}\n")
                    f.write(f"User: {st.session_state.username}\n")
                    f.write(f"Session transfer mode: separate_browsers\n")

                # Close temporary browser
                try:
                    st.session_state.temp_auth_driver.quit()
                    del st.session_state.temp_auth_driver
                    st.success("Temporary browser closed")
                except Exception as e:
                    st.warning(f"⚠️ Could not close temporary browser: {e}")

                st.success(" Authentication session transferred successfully!")
                st.success(" Background worker will create testing browser with your authentication.")
                st.info(" **Session transfer complete** - Testing will use separate persistent browser.")

                # Clean up session state
                cleanup_auth_session()

                # Redirect to dashboard
                time.sleep(3)
                st.session_state.current_page = 'dashboard'
                st.rerun()

            else:
                st.error(" Failed to extract session data - please try authentication again")
                # Reset to allow retry
                st.session_state.auth_step = 'browser_opening'
                if st.button(" Try Again"):
                    st.rerun()

        except Exception as e:
            st.error(f" Session transfer failed: {e}")
            st.error(" **Please try the authentication process again**")

            # Clean up and reset
            cleanup_auth_session()
            if st.button(" Try Again"):
                st.session_state.auth_test_id = test_id
                st.session_state.auth_step = 'browser_opening'
                st.rerun()


def extract_session_data_from_temp_browser(temp_driver):
    """Extract cookies and session data from temporary authentication browser - Fixed logger issue"""
    try:
        # Get all cookies from the authenticated session
        cookies = temp_driver.get_cookies()

        # Get current URL to understand the domain
        current_url = temp_driver.current_url
        page_title = temp_driver.title

        # Validate that we have a meaningful session
        if not cookies:
            st.warning("⚠️ No cookies found in temporary browser")
            return None

        # Try to get local storage data (if accessible)
        local_storage = {}
        try:
            local_storage = temp_driver.execute_script("return Object.assign({}, window.localStorage);")
        except Exception as e:
            # LocalStorage access failed - this is normal in some cases
            pass

        # Try to get session storage data (if accessible)
        session_storage = {}
        try:
            session_storage = temp_driver.execute_script("return Object.assign({}, window.sessionStorage);")
        except Exception as e:
            # SessionStorage access failed - this is normal in some cases
            pass

        session_data = {
            'cookies': cookies,
            'current_url': current_url,
            'page_title': page_title,
            'local_storage': local_storage,
            'session_storage': session_storage,
            'timestamp': datetime.now().isoformat(),
            'domain': current_url.split('/')[2] if '/' in current_url else None
        }

        # Show success info to user
        st.success(f" Session data extracted: {len(cookies)} cookies from {session_data['domain']}")
        st.info(f"📄 Current page: {page_title}")

        return session_data

    except Exception as e:
        st.error(f" Failed to extract session data: {e}")
        return None


def ensure_background_worker():
    """Ensure background worker is running with better error handling"""
    try:
        import subprocess
        import sys
        import os

        # Check if background_worker.py exists
        if not os.path.exists("background_worker.py"):
            st.error(" background_worker.py file not found in current directory")
            return False

        # Check if worker is already running by looking for recent log activity
        if os.path.exists("worker.log"):
            import time
            log_time = os.path.getmtime("worker.log")
            current_time = time.time()
            if current_time - log_time < 60:  # 1 minute
                st.success(" Background worker appears to be running")
                return True

        # Try to start background worker
        st.info(" Attempting to start background worker...")

        # Different approaches for different OS
        if os.name == 'nt':  # Windows
            subprocess.Popen([sys.executable, "background_worker.py"],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:  # Linux/Mac
            subprocess.Popen([sys.executable, "background_worker.py"])

        st.success(" Background worker started successfully")
        return True

    except FileNotFoundError:
        st.error(" Python executable not found. Please start worker manually.")
        return False
    except PermissionError:
        st.error(" Permission denied. Please start worker manually.")
        return False
    except Exception as e:
        st.error(f" Could not start background worker: {str(e)}")
        st.info(" **Manual Start**: Open terminal and run `python background_worker.py`")
        return False

# =============================================================================
# TEST HISTORY WITH DELETE FUNCTIONALITY
# =============================================================================

def show_test_history():
    """Test history page with checkbox selection and bulk delete"""
    st.header("Test History")

    # Get user's test runs
    test_runs = db_manager.get_user_test_runs(st.session_state.user_id)

    if not test_runs:
        st.info("No tests found. Create your first test in the 'New Test' tab.")
        return

    # Initialize session state for selected tests if not exists
    if 'selected_tests' not in st.session_state:
        st.session_state.selected_tests = []

    # Filter controls and bulk actions at top
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        databases = db_manager.get_user_databases(st.session_state.user_id)
        selected_db = st.selectbox("Filter by Database", ["All"] + databases)

    with col2:
        statuses = ["All", "completed", "running", "pending", "waiting_login", "failed"]
        selected_status = st.selectbox("Filter by Status", statuses)

    with col3:
        # Select/Deselect All button
        if st.button("Select All", use_container_width=True):
            st.session_state.selected_tests = [t.id for t in test_runs]
            st.rerun()

    with col4:
        # Clear selection button
        if st.button("Clear Selection", use_container_width=True):
            st.session_state.selected_tests = []
            st.rerun()

    # Bulk Delete Section
    if st.session_state.selected_tests:
        selected_count = len(st.session_state.selected_tests)

        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.info(f" {selected_count} test(s) selected")

        with col2:
            if st.button(f"🗑️ Delete Selected ({selected_count})",
                         type="secondary", use_container_width=True):
                if 'confirm_bulk_delete_selected' not in st.session_state:
                    st.session_state.confirm_bulk_delete_selected = True
                    st.rerun()
                else:
                    # Perform bulk delete
                    with st.spinner(f"Deleting {selected_count} selected tests..."):
                        selected_tests = [t for t in test_runs if t.id in st.session_state.selected_tests]
                        success_count = delete_multiple_tests(selected_tests)
                        st.success(f"Deleted {success_count} tests successfully!")

                        # Clear selections and confirmation
                        st.session_state.selected_tests = []
                        del st.session_state.confirm_bulk_delete_selected
                        time.sleep(2)
                        st.rerun()

        with col3:
            if 'confirm_bulk_delete_selected' in st.session_state:
                if st.button(" Cancel", use_container_width=True):
                    del st.session_state.confirm_bulk_delete_selected
                    st.rerun()

        # Show confirmation message
        if 'confirm_bulk_delete_selected' in st.session_state:
            st.warning(
                f"⚠️ This will permanently delete {selected_count} selected tests and all their data. Click 'Delete Selected' again to confirm.")

    # Additional bulk actions
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        # Delete all completed tests
        completed_tests = [t for t in test_runs if t.status == 'completed']
        if completed_tests:
            if st.button(f"Delete All Completed ({len(completed_tests)})", type="secondary"):
                if 'confirm_delete_completed' not in st.session_state:
                    st.session_state.confirm_delete_completed = True
                    st.warning(f"This will delete {len(completed_tests)} completed tests and their data.")
                    st.info("Click the button again to confirm deletion.")
                else:
                    with st.spinner("Deleting completed tests..."):
                        success_count = delete_multiple_tests(completed_tests)
                        st.success(f"Deleted {success_count} completed tests")
                        del st.session_state.confirm_delete_completed
                        time.sleep(2)
                        st.rerun()

    with col2:
        # Delete all stuck tests
        stuck_tests = [t for t in test_runs if t.status in ['pending', 'waiting_login', 'running']]
        if stuck_tests:
            if st.button(f"Delete All Stuck ({len(stuck_tests)})", type="secondary"):
                if 'confirm_delete_stuck' not in st.session_state:
                    st.session_state.confirm_delete_stuck = True
                    st.warning(f"This will delete {len(stuck_tests)} stuck tests")
                    st.info("Click again to confirm")
                else:
                    with st.spinner("Deleting stuck tests..."):
                        success_count = delete_multiple_tests(stuck_tests)
                        st.success(f"Deleted {success_count} stuck tests")
                        del st.session_state.confirm_delete_stuck
                        time.sleep(2)
                        st.rerun()

    # Reset confirmations if different action is taken
    if 'confirm_delete_completed' in st.session_state and st.button("Cancel Bulk Delete Completed"):
        del st.session_state.confirm_delete_completed
        st.rerun()

    if 'confirm_delete_stuck' in st.session_state and st.button("Cancel Bulk Delete Stuck"):
        del st.session_state.confirm_delete_stuck
        st.rerun()

    # Filter test runs
    filtered_tests = test_runs
    if selected_db != "All":
        filtered_tests = [t for t in filtered_tests if t.database_name == selected_db]
    if selected_status != "All":
        filtered_tests = [t for t in filtered_tests if t.status == selected_status]

    st.info(f"Showing {len(filtered_tests)} of {len(test_runs)} tests")

    # Display tests with checkboxes
    for test in filtered_tests:
        with st.container():
            # Create columns: Checkbox, Test Info, Status, Date, Results, Action
            col1, col2, col3, col4, col5, col6 = st.columns([0.5, 3, 2, 2, 2, 1])

            with col1:
                # Checkbox for selection
                is_selected = test.id in st.session_state.selected_tests
                if st.checkbox("Select", value=is_selected, key=f"select_{test.id}", label_visibility="collapsed"):
                    if test.id not in st.session_state.selected_tests:
                        st.session_state.selected_tests.append(test.id)
                else:
                    if test.id in st.session_state.selected_tests:
                        st.session_state.selected_tests.remove(test.id)

            with col2:
                st.write(f"**{test.test_name}**")
                st.caption(f"Database: {test.database_name}")
                st.caption(f"URLs: {test.total_urls}")

            with col3:
                # Status display with proper logic
                if test.status == 'running':
                    st.markdown(f'<div class="job-status-running">In-Progress ({test.progress:.0f}%)</div>',
                                unsafe_allow_html=True)
                elif test.status == 'completed':
                    st.markdown(f'<div class="job-status-completed">Completed</div>', unsafe_allow_html=True)
                    if test.success_rate is not None:
                        st.caption(f"Success: {test.success_rate:.1f}%")
                elif test.status == 'failed':
                    # Check if it has results but marked as failed
                    results = db_manager.get_test_results(test.id)
                    if results:
                        st.markdown(f'<div class="job-status-completed">Completed</div>', unsafe_allow_html=True)
                        passed = len([r for r in results if r.status == 'PASS'])
                        failed = len([r for r in results if r.status == 'FAIL'])
                        st.caption(f"P:{passed} F:{failed}")
                    else:
                        st.markdown(f'<div class="job-status-failed">Failed</div>', unsafe_allow_html=True)
                elif test.status == 'waiting_login':
                    st.markdown(f'<div class="job-status-waiting">Waiting Auth</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="job-status-pending">Pending</div>', unsafe_allow_html=True)

            with col4:
                st.write(f"Date: {test.created_date.strftime('%Y-%m-%d')}")
                st.caption(f"{test.created_date.strftime('%H:%M')}")

            with col5:
                # Show results summary
                results = db_manager.get_test_results(test.id)
                if results:
                    passed = len([r for r in results if r.status == 'PASS'])
                    failed = len([r for r in results if r.status == 'FAIL'])
                    st.write(f"Processed: {len(results)}")
                    st.caption(f"Passed: {passed}")
                    st.caption(f"Failed: {failed}")
                elif test.status == 'completed':
                    st.write(f"Passed: {test.passed}")
                    st.write(f"Failed: {test.failed}")
                    if test.skipped > 0:
                        st.caption(f"Skipped: {test.skipped}")

            with col6:
                # Action button (View or Auth)
                results = db_manager.get_test_results(test.id)
                if results:
                    if st.button("View", key=f"view_{test.id}", help="View Results", use_container_width=True):
                        st.session_state.selected_test_id = test.id
                        st.session_state.current_page = 'view_results'
                        st.rerun()
                elif test.status in ['running', 'pending']:
                    if st.button("Retry", key=f"retry_{test.id}", help="Retry Test", use_container_width=True):
                        db_manager.update_test_run_status(test.id, 'waiting_login', 0.0)
                        st.success("Test reset for retry")
                        time.sleep(1)
                        st.rerun()
                elif test.status == 'waiting_login':
                    if st.button("Auth", key=f"auth_{test.id}", help="Authenticate", use_container_width=True):
                        st.session_state.current_page = 'manual_auth'
                        st.rerun()

        st.markdown("---")

# =============================================================================
# RESULTS VIEWING
# =============================================================================

def show_view_results():
    """Enhanced results viewing with test selection capability"""

    # Get all user's tests with results
    user_tests = db_manager.get_user_test_runs(st.session_state.user_id)
    tests_with_results = []

    for test in user_tests:
        try:
            # Check if test has results
            if hasattr(db_manager, 'get_test_results'):
                results = db_manager.get_test_results(test.id)
            else:
                from database import TestResult
                results = db_manager.session.query(TestResult).filter(
                    TestResult.test_run_id == test.id
                ).all()

            if results and len(results) > 0:
                tests_with_results.append({
                    'test': test,
                    'results_count': len(results)
                })
        except:
            continue

    if not tests_with_results:
        st.error("No tests with results found")
        if st.button("Back to History"):
            st.session_state.current_page = 'history'
            st.rerun()
        return

    # Header with test selection
    col1, col2 = st.columns([3, 1])

    with col1:
        st.header("View Test Results")

        # Test selection dropdown
        test_options = {}
        for item in tests_with_results:
            test = item['test']
            count = item['results_count']
            display_name = f"{test.test_name} | {test.database_name} | {count} URLs | {test.created_date.strftime('%Y-%m-%d %H:%M')}"
            test_options[display_name] = test.id

        # Check if we have a pre-selected test
        current_selection = 0
        if 'selected_test_id' in st.session_state:
            for idx, (display_name, test_id) in enumerate(test_options.items()):
                if test_id == st.session_state.selected_test_id:
                    current_selection = idx
                    break

        selected_test_display = st.selectbox(
            "Select Test to View:",
            options=list(test_options.keys()),
            index=current_selection,
            help="Choose which test results you want to view"
        )

        # Get selected test ID
        selected_test_id = test_options[selected_test_display]

        # Update session state with selected test
        st.session_state.selected_test_id = selected_test_id

    with col2:
        st.write("")  # Spacer
        if st.button("Back to History", use_container_width=True):
            st.session_state.current_page = 'history'
            st.rerun()

    # Get the selected test details
    test_run = db_manager.get_test_run_by_id(selected_test_id)
    if not test_run:
        st.error("Selected test not found")
        return

    # Show selected test info
    st.info(
        f"**Viewing:** {test_run.test_name} | **Database:** {test_run.database_name} | **Date:** {test_run.created_date.strftime('%Y-%m-%d %H:%M')} | **Test ID:** {test_run.id}")

    # Get results for the selected test
    try:
        if hasattr(db_manager, 'get_test_results'):
            results = db_manager.get_test_results(selected_test_id)
        else:
            from database import TestResult
            results = db_manager.session.query(TestResult).filter(
                TestResult.test_run_id == selected_test_id
            ).order_by(TestResult.row_number).all()

    except Exception as e:
        st.error(f"Error retrieving results: {e}")

        # Debug information
        with st.expander("Database Debug Information"):
            st.write(f"Test ID: {selected_test_id}")
            st.write(f"Error: {str(e)}")
            st.write(f"Database Manager Type: {type(db_manager)}")

            # Try to show available methods
            try:
                methods = [method for method in dir(db_manager) if not method.startswith('_')]
                st.write(f"Available DB methods: {methods}")
            except:
                pass

            # Try alternative query approach
            try:
                st.write("Attempting alternative query...")
                all_results = db_manager.session.execute(
                    "SELECT * FROM test_results WHERE test_run_id = ?",
                    (selected_test_id,)
                ).fetchall()
                st.write(f"Found {len(all_results)} results using raw SQL")
            except Exception as e2:
                st.write(f"Raw SQL also failed: {e2}")
        return

    if not results:
        st.warning(f"No results found for test ID {selected_test_id}")
        return

    # Load original file for additional columns
    original_df = None
    try:
        file_path = f"uploads/{test_run.uploaded_filename}"
        if os.path.exists(file_path):
            if test_run.uploaded_filename.endswith('.csv'):
                original_df = pd.read_csv(file_path)
            else:
                original_df = pd.read_excel(file_path)
    except Exception as e:
        st.warning(f"Could not load original file: {e}")

    # Verification: Ensure all results belong to selected test
    results_test_ids = list(set([r.test_run_id for r in results]))
    if len(results_test_ids) > 1 or (results_test_ids and results_test_ids[0] != selected_test_id):
        st.error(f"Data integrity issue: Results contain data from multiple tests: {results_test_ids}")
        st.error(f"Expected only test ID: {selected_test_id}")
        return

    # Success message
    st.success(f"Showing {len(results)} results for: {test_run.test_name}")

    # Enhanced Statistics Dashboard
    col1, col2, col3, col4, col5 = st.columns(5)

    passed_count = len([r for r in results if r.status == 'PASS'])
    failed_count = len([r for r in results if r.status == 'FAIL'])
    screenshot_count = len([r for r in results if r.screenshot_filename])

    with col1:
        st.metric("Total URLs", len(results))
    with col2:
        st.metric("Passed", passed_count, delta=f"{(passed_count / len(results) * 100):.1f}%")
    with col3:
        st.metric("Failed", failed_count, delta=f"{(failed_count / len(results) * 100):.1f}%")
    with col4:
        st.metric("Screenshots", screenshot_count, delta=f"{(screenshot_count / len(results) * 100):.1f}%")
    with col5:
        success_rate = (passed_count / len(results)) * 100 if results else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Summary", "Analytics", "Screenshots", "Failed Analysis", "Downloads"])

    with tab1:
        # SUMMARY TAB CONTENT
        st.subheader("Test Results Summary")

        # Create results dataframe for display
        results_data = []
        for result in results:
            # Get additional data from original file
            smenu_type = ""
            caption = ""
            if original_df is not None and result.row_number < len(original_df):
                try:
                    row_data = original_df.iloc[result.row_number]

                    # Look for smenuType column variants
                    smenu_cols = ['smenuType', 'sMenuType', 'MenuType', 'Type', 'smenuttype', 'menu_type']
                    for col in smenu_cols:
                        if col in original_df.columns and pd.notna(row_data[col]):
                            smenu_type = str(row_data[col])
                            break

                    # Look for Caption column variants
                    caption_cols = ['Caption', 'caption', 'Description', 'Name', 'Title']
                    for col in caption_cols:
                        if col in original_df.columns and pd.notna(row_data[col]):
                            caption = str(row_data[col])
                            break
                except:
                    pass

            # Screenshot filename display
            screenshot_display = ""
            if result.screenshot_filename:
                screenshot_display = result.screenshot_filename
            else:
                screenshot_display = "No screenshot"

            results_data.append({
                'Row': result.row_number + 1,
                'URL_Display': result.url[:80] + "..." if len(result.url) > 80 else result.url,
                'Full_URL': result.url,
                'Status': result.status,
                'MenuType': smenu_type,
                'Caption': caption,
                'Screenshot': screenshot_display,
                'Error_Message': result.error_message[:100] + "..." if result.error_message and len(
                    result.error_message) > 100 else (result.error_message or ""),
                'Page_Title': result.page_title[:50] + "..." if result.page_title and len(result.page_title) > 50 else (
                        result.page_title or ""),
                'Screenshot_Filename': result.screenshot_filename or ""
            })

        df = pd.DataFrame(results_data)

        # Filter options
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.selectbox("Filter by Status", ["All", "PASS", "FAIL"])
        with col2:
            screenshot_filter = st.selectbox("Filter by Screenshot", ["All", "With Screenshots", "No Screenshots"])

        # Apply filters
        filtered_df = df.copy()
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df['Status'] == status_filter]
        if screenshot_filter == "With Screenshots":
            filtered_df = filtered_df[filtered_df['Screenshot'] != "No screenshot"]
        elif screenshot_filter == "No Screenshots":
            filtered_df = filtered_df[filtered_df['Screenshot'] == "No screenshot"]

        st.info(f"Showing {len(filtered_df)} of {len(df)} results")

        # Display results table
        display_df = filtered_df[
            ['Row', 'Full_URL', 'Status', 'MenuType', 'Caption', 'Screenshot', 'Error_Message']].copy()

        # Rename columns for better display
        display_df.columns = ['Row #', 'Complete URL', 'Status', 'Menu Type', 'Caption', 'Screenshot Filename',
                              'Error Details']

        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "Row #": st.column_config.NumberColumn("Row #", width="small"),
                "Complete URL": st.column_config.TextColumn("Complete URL", width="large"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Menu Type": st.column_config.TextColumn("Menu Type", width="medium"),
                "Caption": st.column_config.TextColumn("Caption", width="medium"),
                "Screenshot Filename": st.column_config.TextColumn("Screenshot Filename", width="medium"),
                "Error Details": st.column_config.TextColumn("Error Details", width="large")
            },
            hide_index=True
        )

    with tab2:
        # ANALYTICS TAB CONTENT
        st.subheader("Test Analytics")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Error Distribution")
            error_results = [r for r in results if r.status == 'FAIL']

            if error_results:
                error_types = {}
                for result in error_results:
                    if result.error_message:
                        error_msg = result.error_message.lower()
                        if 'timeout' in error_msg:
                            error_types['Timeout'] = error_types.get('Timeout', 0) + 1
                        elif 'not found' in error_msg or '404' in error_msg:
                            error_types['Page Not Found'] = error_types.get('Page Not Found', 0) + 1
                        elif 'access denied' in error_msg or 'forbidden' in error_msg:
                            error_types['Access Denied'] = error_types.get('Access Denied', 0) + 1
                        elif 'invalid' in error_msg:
                            error_types['Invalid Page'] = error_types.get('Invalid Page', 0) + 1
                        else:
                            error_types['Other'] = error_types.get('Other', 0) + 1
                    else:
                        error_types['Unknown'] = error_types.get('Unknown', 0) + 1

                for error_type, count in error_types.items():
                    percentage = (count / len(error_results)) * 100
                    st.write(f"**{error_type}**: {count} ({percentage:.1f}%)")
            else:
                st.success("No errors found!")

        with col2:
            st.markdown("#### Test Coverage")

            screenshot_coverage = (len([r for r in results if r.screenshot_filename]) / len(results)) * 100
            st.write(f"**Screenshot Coverage**: {screenshot_coverage:.1f}%")

            status_dist = {}
            for result in results:
                status_dist[result.status] = status_dist.get(result.status, 0) + 1

            for status, count in status_dist.items():
                percentage = (count / len(results)) * 100
                st.write(f"**{status}**: {count} ({percentage:.1f}%)")

        # Menu Type Analysis (if available)
        if original_df is not None:
            st.markdown("#### Menu Type Analysis")
            menu_analysis = {}
            for result in results:
                if result.row_number < len(original_df):
                    try:
                        row_data = original_df.iloc[result.row_number]
                        smenu_cols = ['smenuType', 'sMenuType', 'MenuType', 'Type']
                        menu_type = "Unknown"
                        for col in smenu_cols:
                            if col in original_df.columns and pd.notna(row_data[col]):
                                menu_type = str(row_data[col])
                                break

                        if menu_type not in menu_analysis:
                            menu_analysis[menu_type] = {'total': 0, 'passed': 0, 'failed': 0}

                        menu_analysis[menu_type]['total'] += 1
                        if result.status == 'PASS':
                            menu_analysis[menu_type]['passed'] += 1
                        else:
                            menu_analysis[menu_type]['failed'] += 1
                    except:
                        pass

            if menu_analysis:
                for menu_type, stats in menu_analysis.items():
                    success_rate = (stats['passed'] / stats['total']) * 100 if stats['total'] > 0 else 0
                    st.write(f"**{menu_type}**: {stats['total']} total, {success_rate:.1f}% success rate")

    with tab3:
        # SCREENSHOTS TAB CONTENT
        st.subheader("Screenshots Gallery")

        screenshot_results = [r for r in results if r.screenshot_filename]

        if not screenshot_results:
            st.info("No screenshots were captured for this test.")
        else:
            # Gallery controls
            col1, col2, col3 = st.columns([1, 1, 2])

            with col1:
                gallery_filter = st.selectbox("Show Screenshots", ["All", "PASS Only", "FAIL Only"],
                                              key="gallery_filter")

            with col2:
                per_page = st.selectbox("Screenshots per page", [6, 12, 24], index=1)

            with col3:
                if st.button("Download All Screenshots ZIP", type="primary"):
                    try:
                        zip_data = create_screenshots_zip_from_results(test_run.id, screenshot_results)
                        st.download_button(
                            label="Download ZIP File",
                            data=zip_data,
                            file_name=f"screenshots_test_{test_run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip"
                        )
                        st.success("ZIP file ready for download!")
                    except Exception as e:
                        st.error(f"Error creating ZIP: {e}")

            # Filter screenshots
            if gallery_filter == "PASS Only":
                display_screenshots = [r for r in screenshot_results if r.status == 'PASS']
            elif gallery_filter == "FAIL Only":
                display_screenshots = [r for r in screenshot_results if r.status == 'FAIL']
            else:
                display_screenshots = screenshot_results

            st.info(f"Displaying {len(display_screenshots)} screenshots")

            # Display screenshots in grid
            if display_screenshots:
                cols = st.columns(3)
                for idx, result in enumerate(display_screenshots[:per_page]):
                    col_idx = idx % 3

                    with cols[col_idx]:
                        if result.status == 'PASS':
                            st.success(f"Row {result.row_number + 1} - PASS")
                        else:
                            st.error(f"Row {result.row_number + 1} - FAIL")

                        st.caption(f"URL: {result.url[:50]}...")

                        # Show menu type and caption if available
                        if original_df is not None and result.row_number < len(original_df):
                            try:
                                row_data = original_df.iloc[result.row_number]
                                smenu_cols = ['smenuType', 'sMenuType', 'MenuType', 'Type']
                                for col in smenu_cols:
                                    if col in original_df.columns and pd.notna(row_data[col]):
                                        st.caption(f"**Type:** {row_data[col]}")
                                        break

                                caption_cols = ['Caption', 'caption', 'Description', 'Name']
                                for col in caption_cols:
                                    if col in original_df.columns and pd.notna(row_data[col]):
                                        st.caption(f"**Caption:** {row_data[col]}")
                                        break
                            except:
                                pass

                        screenshot_path = f"screenshots/test_{test_run.id}/{result.screenshot_filename}"
                        if os.path.exists(screenshot_path):
                            try:
                                image = Image.open(screenshot_path)
                                st.image(image, use_container_width=True)

                                with open(screenshot_path, 'rb') as f:
                                    st.download_button(
                                        "Download",
                                        f.read(),
                                        file_name=f"screenshot_row_{result.row_number + 1}.png",
                                        mime="image/png",
                                        key=f"dl_{result.id}"
                                    )
                            except Exception as e:
                                st.error(f"Error loading screenshot: {e}")
                        else:
                            st.warning("Screenshot file not found")

                        if result.status == 'FAIL' and result.error_message:
                            with st.expander("Error Details"):
                                st.text(result.error_message[:200])

    with tab4:
        # FAILED ANALYSIS TAB CONTENT
        st.subheader("Failed Test Analysis")

        failed_results = [r for r in results if r.status == 'FAIL']
        if failed_results:
            st.info(f"Found {len(failed_results)} failed tests")

            for i, failed_result in enumerate(failed_results, 1):
                with st.expander(f"Failed Test #{i} - Row {failed_result.row_number + 1}"):
                    st.write(f"**URL:** {failed_result.url}")

                    # Show original file data
                    if original_df is not None and failed_result.row_number < len(original_df):
                        try:
                            row_data = original_df.iloc[failed_result.row_number]

                            smenu_cols = ['smenuType', 'sMenuType', 'MenuType', 'Type']
                            for col in smenu_cols:
                                if col in original_df.columns and pd.notna(row_data[col]):
                                    st.write(f"**Menu Type:** {row_data[col]}")
                                    break

                            caption_cols = ['Caption', 'caption', 'Description', 'Name']
                            for col in caption_cols:
                                if col in original_df.columns and pd.notna(row_data[col]):
                                    st.write(f"**Caption:** {row_data[col]}")
                                    break
                        except:
                            pass

                    if failed_result.error_message:
                        st.write(f"**Error Details:** {failed_result.error_message}")

                    if failed_result.page_title:
                        st.write(f"**Page Title:** {failed_result.page_title}")

                    if failed_result.screenshot_filename:
                        st.write(f"**Screenshot:** Available")
                        screenshot_path = f"screenshots/test_{test_run.id}/{failed_result.screenshot_filename}"
                        if os.path.exists(screenshot_path):
                            try:
                                image = Image.open(screenshot_path)
                                st.image(image, caption=f"Failed test screenshot", width=400)
                            except Exception as e:
                                st.error(f"Error loading screenshot: {e}")
                    else:
                        st.write("**Screenshot:** Not available")
        else:
            st.success("No failed tests found - all URLs passed!")

    with tab5:
        # DOWNLOADS TAB CONTENT
        st.subheader("Download Options")

        col1, col2, col3 = st.columns(3)

        with col1:
            # Download CSV
            if 'df' in locals() and len(df) > 0:
                # Create download dataframe with all complete information
                download_df = df[
                    ['Row', 'Full_URL', 'Status', 'MenuType', 'Caption', 'Screenshot_Filename', 'Error_Message',
                     'Page_Title']].copy()

                # Rename columns for CSV
                download_df.columns = [
                    'Row_Number',
                    'Complete_URL',
                    'Test_Status',
                    'Menu_Type',
                    'Caption',
                    'Screenshot_Filename',
                    'Error_Message',
                    'Page_Title'
                ]

                csv_data = download_df.to_csv(index=False)

                st.download_button(
                    "Download Results CSV",
                    csv_data,
                    file_name=f"test_results_{test_run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Download complete results with full URLs and screenshot filenames"
                )
            else:
                st.error("No data available for download")

        with col2:
            # Download Screenshots ZIP
            if screenshot_results:
                if st.button("Create Screenshots ZIP", use_container_width=True, type="primary"):
                    try:
                        zip_data = create_screenshots_zip_from_results(test_run.id, screenshot_results)
                        st.download_button(
                            "Download Screenshots ZIP",
                            zip_data,
                            file_name=f"screenshots_test_{test_run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            help="Download ZIP containing all screenshot files",
                            use_container_width=True
                        )
                        st.success("ZIP created successfully!")
                    except Exception as e:
                        st.error(f"Error creating ZIP: {e}")
            else:
                st.info("No screenshots to download")

        with col3:
            # Generate Report
            if st.button("Generate Enhanced Report", use_container_width=True, type="primary"):
                try:
                    # Use the existing simple report function
                    report_content = generate_test_report_simple(test_run, results)
                    st.download_button(
                        "Download Test Report",
                        report_content,
                        file_name=f"test_report_{test_run.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        help="Download detailed test report",
                        use_container_width=True
                    )
                    st.success("Report generated successfully!")
                except Exception as e:
                    st.error(f"Error generating report: {e}")


def generate_test_report_simple(test_run, results):
    """Generate simple test report"""
    passed = len([r for r in results if r.status == 'PASS'])
    failed = len([r for r in results if r.status == 'FAIL'])
    screenshots = len([r for r in results if r.screenshot_filename])

    report_lines = [
        "TEST REPORT",
        "=" * 50,
        f"Test Name: {test_run.test_name}",
        f"Database: {test_run.database_name}",
        f"Date: {test_run.created_date}",
        f"Status: {test_run.status}",
        "",
        "SUMMARY",
        "-" * 20,
        f"Total URLs: {len(results)}",
        f"Passed: {passed}",
        f"Failed: {failed}",
        f"Screenshots: {screenshots}",
        f"Success Rate: {(passed / len(results) * 100):.1f}%",
        "",
        "DETAILED RESULTS",
        "-" * 30
    ]

    for result in results:
        report_lines.extend([
            f"Row {result.row_number + 1}: {result.status}",
            f"URL: {result.url}",
        ])

        if result.screenshot_filename:
            report_lines.append(f"Screenshot: {result.screenshot_filename}")

        if result.error_message:
            report_lines.append(f"Error: {result.error_message}")

        if result.page_title:
            report_lines.append(f"Title: {result.page_title}")

        report_lines.append("-" * 50)

    report_lines.extend([
        "",
        f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])

    return "\n".join(report_lines)

def generate_enhanced_test_report(test_run, results, original_df):
    """Generate a comprehensive test report with original file data"""
    error_count = sum(1 for r in results if r.status == 'FAIL' and r.error_message)

    report_lines = [
        "=" * 70,
        f"YARDI URL TESTER - ENHANCED TEST REPORT",
        "=" * 70,
        "",
        f"Test Name: {test_run.test_name}",
        f"Database: {test_run.database_name}",
        f"Test Date: {test_run.created_date.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Completion Date: {test_run.completed_date.strftime('%Y-%m-%d %H:%M:%S') if test_run.completed_date else 'N/A'}",
        "",
        "SUMMARY:",
        f"- Total URLs Tested: {test_run.total_urls}",
        f"- Passed: {test_run.passed}",
        f"- Failed: {test_run.failed}",
        f"- Skipped: {test_run.skipped}",
        f"- Success Rate: {test_run.success_rate:.1f}%",
        f"- Error Details Captured: {error_count}",
        "",
        "DETAILED RESULTS:",
        "-" * 70,
    ]

    for result in results:
        # Get original file data
        smenu_type = ""
        caption = ""
        if original_df is not None and result.row_number < len(original_df):
            try:
                row_data = original_df.iloc[result.row_number]

                # Get smenuType
                smenu_cols = ['smenuType', 'sMenuType', 'MenuType', 'Type']
                for col in smenu_cols:
                    if col in original_df.columns and pd.notna(row_data[col]):
                        smenu_type = str(row_data[col])
                        break

                # Get Caption
                caption_cols = ['Caption', 'caption', 'Description', 'Name']
                for col in caption_cols:
                    if col in original_df.columns and pd.notna(row_data[col]):
                        caption = str(row_data[col])
                        break
            except:
                pass

        report_lines.extend([
            f"Row {result.row_number + 1}: {result.status}",
            f"URL: {result.url}",
            f"Menu Type: {smenu_type or 'N/A'}",
            f"Caption: {caption or 'N/A'}",
            f"Screenshot: screenshot{result.row_number + 1}.png" if result.screenshot_filename else "None",
        ])

        if result.status == 'FAIL' and result.error_message:
            # Clean error message
            clean_error = result.error_message
            clean_error = clean_error.replace('EXTRACTED:', '').replace('Browser Error:', '').strip()
            if clean_error:
                report_lines.append(f"Error: {clean_error}")

        report_lines.append("-" * 50)

    report_lines.extend([
        "",
        f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Error Detection: Fast browser-based detection with Playwright",
        "=" * 70
    ])

    return "\n".join(report_lines)


# =============================================================================
# SQL DOWNLOAD
# =============================================================================
# =============================================================================
# SQL GENERATION FUNCTIONS
# =============================================================================

def generate_customized_sql_query(surl, menusetlist):
    """Generate the SQL query with user-provided parameters"""

    # Clean up the inputs
    surl = surl.strip()
    if not surl.endswith('/'):
        surl += '/'

    menusetlist = menusetlist.strip()

    # Generate the SQL query with the user's parameters
    sql_query = f"""/*==========================================================
  Generic Menu and Link Retrieval - Customized Query
  ----------------------------------------------------------
  Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  Base URL: {surl}
  Menu Sets: {menusetlist}
==========================================================*/

DECLARE @sURL           VARCHAR(1000);
DECLARE @MenuSetList    VARCHAR(MAX);

/*===== CONFIGURED PARAMETERS =====*/
SET @sURL        = '{surl}';
SET @MenuSetList = '{menusetlist}';
/*==================================*/

/* Split the MenuSet list into individual values */
;WITH cteMenuSets AS (
    SELECT LTRIM(RTRIM([value])) AS MenuSet
    FROM STRING_SPLIT(@MenuSetList, ',')
)

SELECT DISTINCT
       sMenuSet                                    AS MenuSet,
       smenutitle,
       smenuType,
       scaption                                    AS Caption,
       CASE
            WHEN LEFT(REPLACE(sLink, '"', ''), 2) = '..'
                 THEN @sURL + REPLACE(sLink, '"', '')
            WHEN CHARINDEX('rptpath + ', sLink)  > 0
                 AND CHARINDEX('INTRptPath + ', sLink) = 0
                 THEN @sURL + '../pages/SysSqlScript.aspx?&action=Filter&select=reports/rs_' +
                      REPLACE(REPLACE(sLink, '"', ''), 'rptpath + ', '')
            WHEN CHARINDEX('FncPath + ', sLink)  > 0
                 THEN @sURL + '../pages/SysSqlScript.aspx?&action=Filter&select=functions/fs_' +
                      REPLACE(REPLACE(sLink, '"', ''), 'FncPath + ', '')
            WHEN CHARINDEX('INTRptPath + ', sLink) > 0
                 THEN @sURL + '../pages/SysSqlScript.aspx?&action=Filter&International=-1&select=reports/rs_' +
                      REPLACE(REPLACE(sLink, '"', ''), 'INTRptPath + ', '')
            ELSE REPLACE(sLink, '"', '')
       END                                         AS sLink,
       iOrder,
       rownum,
       ilevel
FROM (
        SELECT
               scap.sMenuSet,
               scap.smenutitle,
               scap.smenuType,
               LTRIM(RTRIM(scap.scaption))            AS scaption,
               LTRIM(RTRIM(slink.slink))              AS slink,
               scap.iOrder,
               scap.rownum,
               scap.ilevel
        FROM (
                SELECT
                       scap.strval                         AS scaption,
                       ROW_NUMBER() OVER (
                             PARTITION BY m.sMenuSet,
                                          m.smenutitle,
                                          m.smenuType,
                                          Mr.iOrder
                             ORDER BY     m.sMenuSet,
                                          m.smenutitle,
                                          m.smenuType,
                                          Mr.iOrder
                       )                                   AS rownum,
                       m.sMenuSet,
                       m.smenutitle,
                       m.smenuType,
                       Mr.iOrder,
                       Mr.hmy,
                       Mr.ilevel
                FROM MenuRef         Mr
                     INNER JOIN menu m
                        ON Mr.hmenu = m.hmy
                     CROSS APPLY dbo.StringSplit(Mr.scaption, ',') scap
                WHERE m.sMenuSet IN (SELECT MenuSet FROM cteMenuSets)
        )  scap
              INNER JOIN (
                  SELECT
                         slink.strval                       AS slink,
                         ROW_NUMBER() OVER (
                               PARTITION BY m.sMenuSet,
                                            m.smenutitle,
                                            m.smenuType,
                                            Mr.iOrder
                               ORDER BY     m.sMenuSet,
                                            m.smenutitle,
                                            m.smenuType,
                                            Mr.iOrder
                         )                                   AS rownum,
                         m.sMenuSet,
                         m.smenutitle,
                         m.smenuType,
                         Mr.iOrder,
                         Mr.hmy
                  FROM MenuRef         Mr
                       INNER JOIN menu m
                          ON Mr.hmenu = m.hmy
                       CROSS APPLY dbo.StringSplit(Mr.slink, ',') slink
                  WHERE m.sMenuSet IN (SELECT MenuSet FROM cteMenuSets)
              ) slink
                 ON  slink.sMenuSet   = scap.sMenuSet
                 AND slink.smenutitle = scap.smenutitle
                 AND slink.smenuType  = scap.smenuType
                 AND slink.iOrder     = scap.iOrder
                 AND slink.hmy        = scap.hmy
                 AND slink.rownum     = scap.rownum
) main
ORDER BY
       sMenuSet,
       smenuType,
       iOrder,
       rownum,
       scaption;

/*==========================================================
  Query Information:
  - This query retrieves menu links from Yardi database
  - It builds complete URLs based on the provided base URL
  - Results include MenuSet, Type, Caption, and full sLink
  - Use the sLink column for URL testing
==========================================================*/"""

    return sql_query


# =============================================================================
# SQL DOWNLOAD - SIMPLIFIED VERSION
# =============================================================================

def show_sql_download():
    """SQL download page with input fields but no SQL display"""
    st.header("Download SQL Query")

    # Initialize session state for form values
    if 'sql_surl' not in st.session_state:
        st.session_state.sql_surl = 'https://yourclientdomain.com/53063/pages/'
    if 'sql_menusetlist' not in st.session_state:
        st.session_state.sql_menusetlist = 'PLD_PMOAAcct'

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Configure SQL Query Parameters")

        # User input form
        with st.form("sql_config_form"):
            st.markdown("### Query Configuration")
            st.info("**Instructions**: Configure the parameters below, then download the customized SQL query.")

            # sURL input
            surl_input = st.text_input(
                "Base URL (sURL) *",
                value=st.session_state.sql_surl,
                placeholder="https://yourclientdomain.com/53063/pages/",
                help="Enter your Yardi domain URL with trailing slash. Example: https://yourclientdomain.com/53063/pages/"
            )

            # MenuSetList input
            menusetlist_input = st.text_area(
                "Menu Set List (MenuSetList) *",
                value=st.session_state.sql_menusetlist,
                placeholder="PLD_PMOAAcct, MENU_SET_2, MENU_SET_3",
                help="Enter one or more MenuSet names separated by commas. Example: PLD_PMOAAcct, MENU_SET_2",
                height=100
            )

            # Generate and Download button (combined)
            if st.form_submit_button("Generate & Download SQL Query", type="primary", use_container_width=True):
                if surl_input.strip() and menusetlist_input.strip():
                    # Update session state
                    st.session_state.sql_surl = surl_input.strip()
                    st.session_state.sql_menusetlist = menusetlist_input.strip()

                    # Generate the SQL query
                    try:
                        customized_sql = generate_customized_sql_query(
                            st.session_state.sql_surl,
                            st.session_state.sql_menusetlist
                        )

                        # Store in session state for download
                        st.session_state.generated_sql = customized_sql
                        st.session_state.sql_ready = True

                        st.success("SQL query generated successfully!")
                        st.rerun()

                    except Exception as e:
                        st.error(f" Error generating SQL query: {e}")
                else:
                    st.error(" Please provide both Base URL and Menu Set List")

        # Show current configuration if SQL is ready
        if st.session_state.get('sql_ready', False):
            st.markdown("---")
            st.subheader(" Query Ready for Download")

            col_a, col_b = st.columns(2)
            with col_a:
                st.success(f"**Base URL**: {st.session_state.sql_surl}")
            with col_b:
                st.success(f"**Menu Sets**: {st.session_state.sql_menusetlist}")

            # Download button
            if 'generated_sql' in st.session_state:
                st.download_button(
                    label="📥 Download Customized SQL Query",
                    data=st.session_state.generated_sql,
                    file_name=f"yardi_menu_query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                    help="Download your customized SQL query file"
                )

    with col2:
        st.subheader("Instructions")
        st.markdown("""
        **How to use:**

        1. **Configure Parameters** (left side):
           - Enter your Yardi Base URL
           - Enter Menu Set names (comma-separated)

        2. **Generate & Download** the SQL query

        3. **Run in Database Tool**:
           - SQL Server Management Studio
           - MySQL Workbench
           - pgAdmin, etc.

        4. **Export Results** as CSV or Excel

        5. **Upload** the file in 'New Test' tab
        """)

        st.subheader("Parameter Examples")
        st.markdown("""
        **Base URL Examples:**
        ```
        https://client.yardipcv.com/12345/pages/
        https://yourcompany.yardi.com/67890/pages/
        https://demo.yardipcv.com/11111/pages/
        ```

        **Menu Set Examples:**
        ```
        PLD_PMOAAcct
        MENU_SET_1, MENU_SET_2
        PLD_PMOAAcct, PLD_Leasing, PLD_Maint
        ```
        """)

        st.subheader("Requirements")
        st.markdown("""
        - Database access permissions
        - Valid Yardi domain URL
        - Correct MenuSet names
        - URLs column in results
        """)

        st.subheader("Query Features")
        st.markdown("""
        - **Dynamic URL Construction**: Builds complete URLs based on link types
        - **Multiple Menu Sets**: Supports comma-separated menu sets
        - **Smart Link Processing**: Handles different Yardi link formats
        - **Structured Output**: Organized by MenuSet, Type, and Order
        """)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_screenshots_zip_from_results(test_run_id, screenshot_results):
    """Create ZIP file from test results"""
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        screenshot_count = 0

        for result in screenshot_results:
            screenshot_path = f"screenshots/test_{test_run_id}/{result.screenshot_filename}"

            if os.path.exists(screenshot_path):
                # Clean URL for filename
                clean_url = "".join(c for c in result.url if c.isalnum() or c in ('-', '_', '.'))[:50]
                zip_filename = f"row_{result.row_number + 1}_{result.status}_{clean_url}.png"

                zip_file.write(screenshot_path, zip_filename)
                screenshot_count += 1

        # Add summary
        summary = f"""Test Results Summary
===================
Test ID: {test_run_id}
Screenshots: {screenshot_count}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Status Legend:
PASS - Page loaded successfully
FAIL - Page failed to load (may include extracted error text)
SKIP - Page was skipped

Features:
- Smart Error Detection: Failed pages have error text extracted from screenshots
- Complete URL Testing: All URLs tested with screenshots
- Enhanced Error Analysis: Browser errors + extracted text

File Naming Convention:
row_[NUMBER]_[STATUS]_[URL_SNIPPET].png
"""
        zip_file.writestr("README.txt", summary)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """Main application logic"""
    if not st.session_state.authenticated:
        login_page()
    else:
        # ensure_background_worker()

        # Check for view_results page
        if st.session_state.current_page == 'view_results':
            show_view_results()
        else:
            dashboard_page()


if __name__ == "__main__":
    main()
