import sqlite3
import hashlib
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging

# Get logger
logger = logging.getLogger(__name__)

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow)


class TestRun(Base):
    __tablename__ = 'test_runs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    database_name = Column(String(100), nullable=False)
    test_name = Column(String(200), nullable=False)
    status = Column(String(20), default='pending')  # pending, running, completed, failed, waiting_login
    progress = Column(Float, default=0.0)
    total_urls = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    created_date = Column(DateTime, default=datetime.utcnow)
    completed_date = Column(DateTime)
    url_column = Column(String(100))
    uploaded_filename = Column(String(255))
    config_filename = Column(String(255))  # NEW: Hybrid detection configuration file
    detection_preset = Column(String(50))  # NEW: Store which preset was used (lightning, balanced, etc.)
    avg_confidence = Column(Float)  # NEW: Average confidence score across all results
    avg_execution_time = Column(Float)  # NEW: Average execution time per URL


class TestResult(Base):
    __tablename__ = 'test_results'

    id = Column(Integer, primary_key=True)
    test_run_id = Column(Integer, nullable=False)
    row_number = Column(Integer, nullable=False)
    url = Column(Text, nullable=False)
    status = Column(String(20), nullable=False)  # PASS, FAIL, SKIP, UNCERTAIN
    screenshot_filename = Column(String(255))
    page_title = Column(Text)
    error_message = Column(Text(2000))  # Increased for OCR data
    processed_date = Column(DateTime, default=datetime.utcnow)

    # NEW: Hybrid detection fields
    confidence = Column(Float)  # Confidence score (0-100)
    execution_time = Column(Float)  # Time taken for analysis in milliseconds
    detection_method = Column(String(100))  # Primary method that determined the result
    evidence = Column(Text)  # JSON string with detailed evidence from all methods
    methods_used = Column(String(500))  # Comma-separated list of methods used


class DatabaseManager:
    def __init__(self, db_path="yardi_tester.db"):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)

        # Create tables first
        Base.metadata.create_all(self.engine)

        Session = sessionmaker(bind=self.engine)
        self.session = Session()

        # Check and migrate database if needed
        self.check_and_migrate_database()

    def check_and_migrate_database(self):
        """Check and migrate database schema if needed"""
        try:
            from sqlalchemy import text

            # Fix: Use text() for raw SQL
            self.session.execute(text("SELECT config_filename FROM test_runs LIMIT 1")).fetchone()

            logger.info("✅ Database schema is up to date")
        except Exception as e:
            logger.warning(f"⚠️ Database schema needs update: {e}")

            # Add the missing column
            try:
                logger.info("🔧 Adding config_filename column...")
                self.session.execute(text("ALTER TABLE test_runs ADD COLUMN config_filename VARCHAR(255)"))
                self.session.commit()
                logger.info("✅ Database schema updated successfully")
            except Exception as migrate_error:
                logger.error(f"💥 Failed to update schema: {migrate_error}")
                self.session.rollback()

    def _migrate_database_schema(self):
        """Apply database schema migrations"""
        try:
            logger.info("🔄 Starting database migration...")

            # Get raw connection for ALTER TABLE statements
            raw_conn = self.engine.raw_connection()
            cursor = raw_conn.cursor()

            # Migrations for test_runs table
            test_run_migrations = [
                ("config_filename", "ALTER TABLE test_runs ADD COLUMN config_filename VARCHAR(255)"),
                ("detection_preset", "ALTER TABLE test_runs ADD COLUMN detection_preset VARCHAR(50)"),
                ("avg_confidence", "ALTER TABLE test_runs ADD COLUMN avg_confidence FLOAT"),
                ("avg_execution_time", "ALTER TABLE test_runs ADD COLUMN avg_execution_time FLOAT")
            ]

            # Migrations for test_results table
            test_result_migrations = [
                ("confidence", "ALTER TABLE test_results ADD COLUMN confidence FLOAT"),
                ("execution_time", "ALTER TABLE test_results ADD COLUMN execution_time FLOAT"),
                ("detection_method", "ALTER TABLE test_results ADD COLUMN detection_method VARCHAR(100)"),
                ("evidence", "ALTER TABLE test_results ADD COLUMN evidence TEXT"),
                ("methods_used", "ALTER TABLE test_results ADD COLUMN methods_used VARCHAR(500)")
            ]

            # Apply test_runs migrations
            for column_name, sql in test_run_migrations:
                try:
                    cursor.execute(sql)
                    logger.info(f"✅ Added test_runs.{column_name}")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug(f"⏭️ Column test_runs.{column_name} already exists")
                    else:
                        logger.warning(f"⚠️ Failed to add test_runs.{column_name}: {e}")

            # Apply test_results migrations
            for column_name, sql in test_result_migrations:
                try:
                    cursor.execute(sql)
                    logger.info(f"✅ Added test_results.{column_name}")
                except Exception as e:
                    if "duplicate column name" in str(e).lower():
                        logger.debug(f"⏭️ Column test_results.{column_name} already exists")
                    else:
                        logger.warning(f"⚠️ Failed to add test_results.{column_name}: {e}")

            # Commit changes
            raw_conn.commit()
            raw_conn.close()

            # Refresh the session
            self.session.close()
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

            logger.info("🎉 Database migration completed successfully!")
            return True

        except Exception as e:
            logger.error(f"💥 Database migration failed: {e}")
            return False

    def create_user(self, username, email, password):
        """Create a new user account"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        user = User(username=username, email=email, password_hash=password_hash)
        self.session.add(user)
        self.session.commit()
        return user.id

    def get_pending_jobs(self):
        """Get all pending test runs for background worker"""
        return self.session.query(TestRun).filter(
            TestRun.status.in_(['pending', 'waiting_login'])
        ).order_by(TestRun.created_date).all()

    def get_waiting_login_jobs(self):
        """Get tests waiting for manual login"""
        return self.session.query(TestRun).filter_by(status='waiting_login').order_by(TestRun.created_date).all()

    def authenticate_user(self, username, password):
        """Authenticate user login"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        user = self.session.query(User).filter_by(username=username, password_hash=password_hash).first()
        return user

    def get_user_by_username(self, username):
        """Get user by username"""
        return self.session.query(User).filter_by(username=username).first()

    def create_test_run(self, user_id, database_name, test_name, total_urls, url_column, uploaded_filename,
                        config_filename=None, detection_preset=None):
        """Create a new test run with hybrid detection support"""
        test_run = TestRun(
            user_id=user_id,
            database_name=database_name,
            test_name=test_name,
            total_urls=total_urls,
            url_column=url_column,
            uploaded_filename=uploaded_filename,
            config_filename=config_filename,
            detection_preset=detection_preset
        )
        self.session.add(test_run)
        self.session.commit()
        return test_run.id

    def update_test_run_status(self, test_run_id, status, progress=None):
        """Update test run status and progress"""
        test_run = self.session.query(TestRun).filter_by(id=test_run_id).first()
        if test_run:
            test_run.status = status
            if progress is not None:
                test_run.progress = progress
            if status == 'completed':
                test_run.completed_date = datetime.utcnow()
            self.session.commit()

    def update_test_run_results(self, test_run_id, passed, failed, skipped, success_rate):
        """Update test run with final results"""
        test_run = self.session.query(TestRun).filter_by(id=test_run_id).first()
        if test_run:
            test_run.passed = passed
            test_run.failed = failed
            test_run.skipped = skipped
            test_run.success_rate = success_rate
            self.session.commit()

    def update_test_run_analytics(self, test_run_id, avg_confidence, avg_execution_time):
        """Update test run with hybrid detection analytics"""
        test_run = self.session.query(TestRun).filter_by(id=test_run_id).first()
        if test_run:
            test_run.avg_confidence = avg_confidence
            test_run.avg_execution_time = avg_execution_time
            self.session.commit()

    def add_test_result(self, test_run_id, row_number, url, status, screenshot_filename=None, page_title=None,
                        error_message=None, confidence=None, execution_time=None, detection_method=None,
                        evidence=None, methods_used=None):
        """Add individual test result with hybrid detection data"""

        # Convert evidence to JSON string if it's a dict
        evidence_str = None
        if evidence:
            if isinstance(evidence, dict):
                evidence_str = json.dumps(evidence)
            else:
                evidence_str = str(evidence)

        # Convert methods_used to comma-separated string if it's a list
        methods_str = None
        if methods_used:
            if isinstance(methods_used, list):
                methods_str = ', '.join(methods_used)
            else:
                methods_str = str(methods_used)

        result = TestResult(
            test_run_id=test_run_id,
            row_number=row_number,
            url=url,
            status=status,
            screenshot_filename=screenshot_filename,
            page_title=page_title,
            error_message=error_message,
            confidence=confidence,
            execution_time=execution_time,
            detection_method=detection_method,
            evidence=evidence_str,
            methods_used=methods_str
        )
        self.session.add(result)
        self.session.commit()

    def get_user_test_runs(self, user_id):
        """Get all test runs for a user"""
        return self.session.query(TestRun).filter_by(user_id=user_id).order_by(TestRun.created_date.desc()).all()

    def get_test_run_by_id(self, test_run_id):
        """Get specific test run"""
        return self.session.query(TestRun).filter_by(id=test_run_id).first()

    def get_test_results(self, test_run_id):
        """Get all results for a test run"""
        return self.session.query(TestResult).filter_by(test_run_id=test_run_id).order_by(TestResult.row_number).all()

    def get_test_results_with_analytics(self, test_run_id):
        """Get test results with additional analytics for hybrid detection"""
        results = self.get_test_results(test_run_id)

        analytics = {
            'total_results': len(results),
            'avg_confidence': 0,
            'avg_execution_time': 0,
            'method_performance': {},
            'confidence_distribution': {'high': 0, 'medium': 0, 'low': 0}
        }

        if results:
            # Calculate averages
            valid_confidence = [r.confidence for r in results if r.confidence is not None]
            valid_execution_time = [r.execution_time for r in results if r.execution_time is not None]

            if valid_confidence:
                analytics['avg_confidence'] = sum(valid_confidence) / len(valid_confidence)

            if valid_execution_time:
                analytics['avg_execution_time'] = sum(valid_execution_time) / len(valid_execution_time)

            # Confidence distribution
            for result in results:
                if result.confidence is not None:
                    if result.confidence >= 80:
                        analytics['confidence_distribution']['high'] += 1
                    elif result.confidence >= 60:
                        analytics['confidence_distribution']['medium'] += 1
                    else:
                        analytics['confidence_distribution']['low'] += 1

            # Method performance
            method_stats = {}
            for result in results:
                if result.detection_method:
                    if result.detection_method not in method_stats:
                        method_stats[result.detection_method] = {'count': 0, 'pass': 0, 'fail': 0, 'avg_confidence': 0,
                                                                 'confidences': []}

                    method_stats[result.detection_method]['count'] += 1
                    if result.status == 'PASS':
                        method_stats[result.detection_method]['pass'] += 1
                    elif result.status == 'FAIL':
                        method_stats[result.detection_method]['fail'] += 1

                    if result.confidence is not None:
                        method_stats[result.detection_method]['confidences'].append(result.confidence)

            # Calculate average confidence per method
            for method, stats in method_stats.items():
                if stats['confidences']:
                    stats['avg_confidence'] = sum(stats['confidences']) / len(stats['confidences'])
                    del stats['confidences']  # Remove raw data

            analytics['method_performance'] = method_stats

        return results, analytics

    def get_user_databases(self, user_id):
        """Get unique database names for a user"""
        results = self.session.query(TestRun.database_name).filter_by(user_id=user_id).distinct().all()
        return [r[0] for r in results]

    def get_detection_method_stats(self, user_id=None):
        """Get statistics about detection method effectiveness"""
        query = self.session.query(TestResult)
        if user_id:
            # Join with TestRun to filter by user
            query = query.join(TestRun).filter(TestRun.user_id == user_id)

        results = query.all()

        method_stats = {}
        for result in results:
            if result.detection_method:
                if result.detection_method not in method_stats:
                    method_stats[result.detection_method] = {
                        'total': 0, 'pass': 0, 'fail': 0, 'uncertain': 0,
                        'avg_confidence': 0, 'avg_time': 0,
                        'confidences': [], 'times': []
                    }

                stats = method_stats[result.detection_method]
                stats['total'] += 1

                if result.status == 'PASS':
                    stats['pass'] += 1
                elif result.status == 'FAIL':
                    stats['fail'] += 1
                else:
                    stats['uncertain'] += 1

                if result.confidence is not None:
                    stats['confidences'].append(result.confidence)

                if result.execution_time is not None:
                    stats['times'].append(result.execution_time)

        # Calculate averages
        for method, stats in method_stats.items():
            if stats['confidences']:
                stats['avg_confidence'] = sum(stats['confidences']) / len(stats['confidences'])
            if stats['times']:
                stats['avg_time'] = sum(stats['times']) / len(stats['times'])

            # Remove raw data arrays
            del stats['confidences']
            del stats['times']

        return method_stats

    def get_hybrid_detection_summary(self, test_run_id):
        """Get a summary of hybrid detection performance for a specific test run"""
        test_run = self.get_test_run_by_id(test_run_id)
        if not test_run:
            return None

        results = self.get_test_results(test_run_id)

        summary = {
            'test_run_info': {
                'id': test_run.id,
                'name': test_run.test_name,
                'preset': test_run.detection_preset,
                'total_urls': test_run.total_urls,
                'status': test_run.status
            },
            'detection_config': None,
            'performance_metrics': {
                'total_time': 0,
                'avg_time_per_url': 0,
                'avg_confidence': 0,
                'method_usage': {},
                'accuracy_by_confidence': {}
            },
            'results_breakdown': {
                'pass': test_run.passed,
                'fail': test_run.failed,
                'uncertain': 0,
                'high_confidence': 0,
                'medium_confidence': 0,
                'low_confidence': 0
            }
        }

        # Load detection configuration if available
        if test_run.config_filename:
            config_path = f"uploads/{test_run.config_filename}"
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        summary['detection_config'] = json.load(f)
                except:
                    pass

        # Calculate performance metrics
        if results:
            execution_times = [r.execution_time for r in results if r.execution_time is not None]
            confidences = [r.confidence for r in results if r.confidence is not None]

            if execution_times:
                summary['performance_metrics']['total_time'] = sum(execution_times)
                summary['performance_metrics']['avg_time_per_url'] = sum(execution_times) / len(execution_times)

            if confidences:
                summary['performance_metrics']['avg_confidence'] = sum(confidences) / len(confidences)

            # Method usage statistics
            for result in results:
                if result.methods_used:
                    methods = [m.strip() for m in result.methods_used.split(',')]
                    for method in methods:
                        if method not in summary['performance_metrics']['method_usage']:
                            summary['performance_metrics']['method_usage'][method] = 0
                        summary['performance_metrics']['method_usage'][method] += 1

                # Confidence distribution
                if result.confidence is not None:
                    if result.confidence >= 80:
                        summary['results_breakdown']['high_confidence'] += 1
                    elif result.confidence >= 60:
                        summary['results_breakdown']['medium_confidence'] += 1
                    else:
                        summary['results_breakdown']['low_confidence'] += 1

                if result.status == 'UNCERTAIN':
                    summary['results_breakdown']['uncertain'] += 1

        return summary

    def close(self):
        """Close database connection"""
        self.session.close()


# Initialize database manager
db_manager = DatabaseManager()