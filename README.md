# Yardi URL Tester Pro

Professional URL Testing Platform with Background Jobs and Advanced Error Detection

## 🚀 Features

- **Professional Authentication System** - Secure user registration and login
- **Smart URL Testing** - Advanced error detection with multiple detection methods
- **Background Processing** - Non-blocking test execution with real-time progress
- **Manual SSO Authentication** - Handle complex authentication flows
- **Screenshot Capture** - Visual evidence of test results
- **Comprehensive Reporting** - Detailed test results with analytics
- **SQL Query Generator** - Generate customized Yardi database queries
- **Batch Processing** - Test hundreds of URLs efficiently

## 🛠️ Technology Stack

- **Frontend**: Streamlit with custom CSS styling
- **Backend**: Python with SQLAlchemy
- **Database**: SQLite (easily upgradeable to PostgreSQL)
- **Web Automation**: Selenium WebDriver
- **Detection Engine**: Hybrid detection with content analysis
- **Authentication**: Session-based authentication with bcrypt

## 📋 Requirements

- Python 3.8+
- Chrome browser (for Selenium automation)
- Internet connection for ChromeDriver management

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/yardi-url-tester-pro.git
cd yardi-url-tester-pro
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Application
```bash
streamlit run main.py
```

### 4. Start Background Worker (Optional)
For background test processing:
```bash
python background_worker.py
```

## 📁 Project Structure

```
yardi-url-tester-pro/
├── main.py                 # Main Streamlit application
├── detection_engine.py     # Error detection algorithms
├── database.py            # Database models and management
├── background_worker.py    # Background job processor
├── styles.css             # Custom CSS styling
├── requirements.txt       # Python dependencies
├── uploads/               # Uploaded test files
├── sessions/              # Authentication sessions
├── screenshots/           # Test result screenshots
└── browser_sessions/      # Browser session data
```


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋‍♂️ Support

For support and questions:
- Create an issue in this repository
- Contact: [ rushabh1907@gmail.com ]

## 🔄 Version History

- **v1.0.0** - Initial release with core functionality
- **v1.1.0** - Added hybrid detection engine
- **v1.2.0** - Enhanced authentication system
- **v1.3.0** - Background processing improvements

---

Built with ❤️ for Yardi professionals worldwide
