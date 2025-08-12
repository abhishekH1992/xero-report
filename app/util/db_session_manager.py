from contextlib import contextmanager
from typing import Generator
from app.database.database import SessionLocal
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class DatabaseSessionManager:
    """Manages database sessions with proper cleanup and error recovery"""
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup and transaction management"""
        session: Session = SessionLocal()
        try:
            yield session
            # If we reach here, no exception occurred, so commit
            session.commit()
            logger.debug("Database session committed successfully")
        except SQLAlchemyError as e:
            # Rollback on any database error
            session.rollback()
            logger.error(f"Database error occurred, session rolled back: {e}")
            raise
        except Exception as e:
            # Rollback on any other error
            session.rollback()
            logger.error(f"Unexpected error occurred, session rolled back: {e}")
            raise
        finally:
            # Always close the session
            session.close()
            logger.debug("Database session closed")
    
    def get_fresh_session(self) -> Session:
        """Get a fresh database session (caller must manage cleanup)"""
        return SessionLocal()
    
    def close_session(self, session: Session) -> None:
        """Safely close a database session"""
        try:
            if session.is_active:
                session.rollback()
            session.close()
            logger.debug("Database session manually closed")
        except Exception as e:
            logger.error(f"Error closing database session: {e}")
    
    def rollback_and_close(self, session: Session) -> None:
        """Rollback and close a session (for error scenarios)"""
        try:
            if session.is_active:
                session.rollback()
            session.close()
            logger.debug("Database session rolled back and closed")
        except Exception as e:
            logger.error(f"Error rolling back and closing session: {e}")
