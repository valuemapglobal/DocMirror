"""
SQL ORM Exporter (Data Shredder)
================================
Provides SQLAlchemy models and a generic shredder to transform the hierarchical
L2 Pydantic schema (CreditReportResultSchema) into flattened RDBMS tables.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.sql import func

from docmirror.models.schemas.credit_report_schema import CreditReportResultSchema

Base = declarative_base()

# --- Relational Table Definitions ---

class SQLReportMaster(Base):
    __tablename__ = 'cr_report_master'

    id = Column(String(64), primary_key=True)
    report_id = Column(String(128))
    report_type = Column(String(64))
    report_time = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subject = relationship("SQLSubject", back_populates="report", uselist=False)
    summary = relationship("SQLCreditSummary", back_populates="report", uselist=False)
    accounts = relationship("SQLCreditAccount", back_populates="report")
    public_records = relationship("SQLPublicRecord", back_populates="report")


class SQLSubject(Base):
    __tablename__ = 'cr_subject_info'

    id = Column(String(64), primary_key=True)
    report_uuid = Column(String(64), ForeignKey('cr_report_master.id'))

    name = Column(String(128))
    id_type = Column(String(64))
    id_number = Column(String(64))
    phone_number = Column(String(64)) # Storing primary

    report = relationship("SQLReportMaster", back_populates="subject")


class SQLCreditSummary(Base):
    __tablename__ = 'cr_summary_metrics'

    id = Column(String(64), primary_key=True)
    report_uuid = Column(String(64), ForeignKey('cr_report_master.id'))

    credit_balance = Column(String(64))
    guarantee_balance = Column(String(64))
    total_accounts = Column(Integer)
    overdue_accounts = Column(Integer)
    unsettled_accounts = Column(Integer)
    overdue_count = Column(Integer)

    report = relationship("SQLReportMaster", back_populates="summary")


class SQLCreditAccount(Base):
    __tablename__ = 'cr_credit_account'

    id = Column(String(64), primary_key=True)
    report_uuid = Column(String(64), ForeignKey('cr_report_master.id'))

    account_type = Column(String(64))  # e.g., 非循环贷账户, 贷记卡
    business_type = Column(String(128)) # e.g., 个人住房商业贷款
    currency = Column(String(32))
    limit_amount = Column(Float)
    balance = Column(Float)
    open_date = Column(String(32))
    status = Column(String(32))
    five_tier_class = Column(String(32))
    overdue_amount = Column(Float)
    overdue_periods = Column(Integer)

    report = relationship("SQLReportMaster", back_populates="accounts")


class SQLPublicRecord(Base):
    __tablename__ = 'cr_public_records'

    id = Column(String(64), primary_key=True)
    report_uuid = Column(String(64), ForeignKey('cr_report_master.id'))

    tax_arrears_count = Column(Integer)
    civil_judgments_count = Column(Integer)
    enforcements_count = Column(Integer)
    admin_penalties_count = Column(Integer)

    report = relationship("SQLReportMaster", back_populates="public_records")


# --- The Shredder Service ---

class SQLShredder:
    """
    Shreds L2 JSON/Pydantic into SQL Tuples and flushes them to the DB.
    """
    def __init__(self, db_uri: str):
        self.engine = create_engine(db_uri)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def import_report(self, schema: CreditReportResultSchema) -> str:
        """
        Maps the nested CreditReportResultSchema natively into SQL RDBMS.
        """
        session = self.SessionLocal()

        try:
            report_uuid = str(uuid.uuid4())

            # 1. Master Table
            master = SQLReportMaster(
                id=report_uuid,
                report_id=schema.report_id,
                report_type=schema.report_subtype,
                report_time=schema.report_date
            )
            session.add(master)

            # 2. Subject Info
            primary_phone = schema.subject.phone_numbers[0] if schema.subject.phone_numbers else ""
            subj = SQLSubject(
                id=str(uuid.uuid4()),
                report_uuid=report_uuid,
                name=schema.subject.name,
                id_type=schema.subject.id_type,
                id_number=schema.subject.id_number,
                phone_number=str(primary_phone)
            )
            session.add(subj)

            # 3. Summary Engine
            summ = SQLCreditSummary(
                id=str(uuid.uuid4()),
                report_uuid=report_uuid,
                credit_balance=schema.credit_summary.credit_balance,
                guarantee_balance=schema.credit_summary.guarantee_balance,
                total_accounts=int(schema.credit_summary.total_accounts),
                overdue_accounts=int(schema.credit_summary.overdue_accounts),
                unsettled_accounts=int(schema.credit_summary.unsettled_accounts),
                overdue_count=int(schema.credit_summary.overdue_count)
            )
            session.add(summ)

            # 4. Loop Accounts
            for acc in schema.credit_accounts:
                db_acc = SQLCreditAccount(
                    id=str(uuid.uuid4()),
                    report_uuid=report_uuid,
                    account_type=acc.account_type,
                    business_type=acc.business_type,
                    currency=acc.currency,
                    limit_amount=float(acc.limit_amount) if acc.limit_amount else 0.0,
                    balance=float(acc.balance) if acc.balance else 0.0,
                    open_date=acc.open_date,
                    status=acc.status,
                    five_tier_class=acc.five_tier_class,
                    overdue_amount=float(acc.overdue_amount) if acc.overdue_amount else 0.0,
                    overdue_periods=int(acc.overdue_periods) if str(acc.overdue_periods).isdigit() else 0
                )
                session.add(db_acc)

            # 5. Public Records
            pub = SQLPublicRecord(
                id=str(uuid.uuid4()),
                report_uuid=report_uuid,
                tax_arrears_count=int(schema.public_records.tax_arrears),
                civil_judgments_count=int(schema.public_records.civil_judgments),
                enforcements_count=int(schema.public_records.enforcements),
                admin_penalties_count=int(schema.public_records.admin_penalties)
            )
            session.add(pub)

            session.commit()
            return report_uuid

        except Exception as e:
            session.rollback()
            raise ValueError(f"Failed to shred L2 document into RDBMS: {e}")
        finally:
            session.close()
