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

## 🔧 Configuration

### Database
The application uses SQLite by default. Database file (`yardi_tester.db`) is created automatically on first run.

### Selenium WebDriver
ChromeDriver is managed automatically via `webdriver-manager`. Chrome browser must be installed on the system.

### File Storage
- **uploads/**: CSV/Excel files with URLs to test
- **screenshots/**: Screenshots captured during testing
- **sessions/**: Temporary authentication session data

## 📊 Usage Workflow

### 1. Authentication
- Register new account or login with existing credentials
- Secure session management with password hashing

### 2. SQL Query Generation
- Navigate to "Download SQL" tab
- Configure your Yardi database parameters
- Download customized SQL query
- Run query in your database tool (SSMS, etc.)
- Export results as CSV/Excel

### 3. Test Submission
- Navigate to "New Test" tab
- Upload CSV/Excel file with URLs
- Configure test parameters
- Submit test job

### 4. Manual Authentication
- Navigate to "Manual Auth" tab
- Complete SSO authentication in temporary browser
- Transfer authenticated session to testing browser

### 5. Results Analysis
- Navigate to "Test History" tab
- View completed test results
- Analyze screenshots and error details
- Download comprehensive reports

## 🔍 Detection Engine

The application uses a hybrid detection engine with multiple methods:

### Content Analysis
- Page source scanning for error patterns
- JavaScript alert detection
- Modal/dialog content extraction
- Title and body text analysis

### Error Patterns
The system detects common Yardi errors including:
- "Invalid select file" errors
- Access denied messages
- Session expiration
- Database connection issues
- Page not found errors

## 🚀 Deployment

### Streamlit Community Cloud
1. Push code to GitHub repository
2. Connect GitHub account to [share.streamlit.io](https://share.streamlit.io)
3. Deploy directly from repository

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run application
streamlit run main.py

# Run background worker (separate terminal)
python background_worker.py
```

## 📝 Environment Variables

For production deployment, configure these environment variables:

```bash
# Database (if using PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/database

# Security
SECRET_KEY=your-secret-key-here

# Selenium (if using remote WebDriver)
SELENIUM_GRID_URL=http://selenium-hub:4444/wd/hub
```

## 🐛 Troubleshooting

### Chrome/ChromeDriver Issues
```bash
# Update ChromeDriver
pip install --upgrade webdriver-manager

# Check Chrome installation
google-chrome --version  # Linux
```

### Database Issues
```bash
# Reset database
rm yardi_tester.db
python -c "from database import DatabaseManager; DatabaseManager()"
```

### Performance Optimization
- Use background worker for large test batches
- Implement database connection pooling for production
- Consider Redis for session storage in production

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙋‍♂️ Support

For support and questions:
- Create an issue in this repository
- Contact: [your-email@example.com]

## 🔄 Version History

- **v1.0.0** - Initial release with core functionality
- **v1.1.0** - Added hybrid detection engine
- **v1.2.0** - Enhanced authentication system
- **v1.3.0** - Background processing improvements

---

Built with ❤️ for Yardi professionals worldwide